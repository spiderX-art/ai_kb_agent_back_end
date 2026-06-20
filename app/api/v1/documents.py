from typing import Annotated
import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager

from app.api.deps import get_current_admin_user, get_current_user
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models import Document, DocumentChunk, KnowledgeBase, User
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentCreate,
    DocumentListResponse,
    DocumentListSortBy,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusUpdate,
    SortOrder,
)
from app.schemas.response import ApiResponse, success_response
from app.services.document_files import (
    delete_document_file,
    document_file_path,
    normalize_document_file_type,
    save_uploaded_document_file,
)
from app.services.document_parsing import (
    apply_document_parse_status,
    rebuild_document_text_chunks,
)
from app.services.knowledge_bases import get_knowledge_base_or_404

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


def _get_document_or_404(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise AppError(
            "文档不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return document


def _to_document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        knowledge_base_name=document.knowledge_base.name,
        file_name=document.file_name,
        file_type=document.file_type,
        file_size=document.file_size,
        has_file=bool(document.storage_path),
        status=document.status,
        parse_progress=document.parse_progress or 0,
        parse_chunk_count=document.parse_chunk_count or 0,
        parse_error_message=document.parse_error_message,
        parse_started_at=document.parse_started_at,
        parse_finished_at=document.parse_finished_at,
        created_by_id=document.created_by_id,
        uploaded_at=document.uploaded_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=ApiResponse[DocumentListResponse])
def list_documents(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    knowledge_base_id: Annotated[int | None, Query(gt=0)] = None,
    status: DocumentStatus | None = None,
    file_type: str | None = None,
    keyword: str | None = None,
    page: Annotated[int, Query(gt=0)] = 1,
    page_size: Annotated[int, Query(gt=0, le=100)] = 10,
    sort_by: DocumentListSortBy = "uploaded_at",
    sort_order: SortOrder = "desc",
) -> ApiResponse[DocumentListResponse]:
    stmt = (
        select(Document)
        .join(Document.knowledge_base)
        .options(contains_eager(Document.knowledge_base))
    )
    count_stmt = select(func.count()).select_from(Document).join(Document.knowledge_base)
    filters = []

    if knowledge_base_id is not None:
        filters.append(Document.knowledge_base_id == knowledge_base_id)

    if status is not None:
        filters.append(Document.status == status)

    if file_type:
        filters.append(Document.file_type == file_type.strip().lstrip(".").upper())

    keyword_text = keyword.strip() if keyword else ""
    if keyword_text:
        filters.append(
            or_(
                Document.file_name.contains(keyword_text),
                KnowledgeBase.name.contains(keyword_text),
            )
        )

    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)

    sort_columns = {
        "uploaded_at": Document.created_at,
        "file_name": Document.file_name,
        "file_type": Document.file_type,
        "status": Document.status,
        "knowledge_base_name": KnowledgeBase.name,
    }
    sort_column = sort_columns[sort_by]
    sort_clause = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    id_tie_breaker = Document.id.asc() if sort_order == "asc" else Document.id.desc()
    offset = (page - 1) * page_size

    total = db.scalar(count_stmt) or 0
    total_pages = (total + page_size - 1) // page_size if total else 0
    documents = db.scalars(
        stmt.order_by(sort_clause, id_tie_breaker).offset(offset).limit(page_size)
    ).all()
    return success_response(
        DocumentListResponse(
            items=[_to_document_response(item) for item in documents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    )


@router.post("", response_model=ApiResponse[DocumentResponse])
def create_document_metadata(
    payload: DocumentCreate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    knowledge_base = get_knowledge_base_or_404(db, payload.knowledge_base_id)
    file_type = normalize_document_file_type(payload.file_name, payload.file_type)

    # 当前阶段只保存文档元数据；后续接入文件存储/解析时仍复用这条记录。
    document = Document(
        knowledge_base_id=knowledge_base.id,
        file_name=payload.file_name,
        file_type=file_type,
        file_size=payload.file_size,
        status="uploaded",
        created_by_id=current_user.id,
    )
    # 列表页直接展示知识库文档数，所以元数据增删时同步维护这个冗余计数。
    knowledge_base.document_count += 1
    db.add(document)
    db.commit()
    db.refresh(document)
    return success_response(_to_document_response(document))


@router.post("/upload", response_model=ApiResponse[DocumentResponse])
def upload_document_file(
    knowledge_base_id: Annotated[int, Form(gt=0)],
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    knowledge_base = get_knowledge_base_or_404(db, knowledge_base_id)
    stored_file = save_uploaded_document_file(
        file,
        knowledge_base_id=knowledge_base.id,
    )

    document = Document(
        knowledge_base_id=knowledge_base.id,
        file_name=stored_file.original_file_name,
        file_type=stored_file.file_type,
        file_size=stored_file.file_size,
        storage_path=stored_file.storage_path,
        stored_file_name=stored_file.stored_file_name,
        content_type=stored_file.content_type,
        status="uploaded",
        created_by_id=current_user.id,
    )
    knowledge_base.document_count += 1
    db.add(document)

    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_document_file(stored_file.storage_path)
        raise

    db.refresh(document)
    return success_response(_to_document_response(document))


@router.get("/{document_id}", response_model=ApiResponse[DocumentResponse])
def get_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    document = _get_document_or_404(db, document_id)
    return success_response(_to_document_response(document))


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    document = _get_document_or_404(db, document_id)
    if not document.storage_path:
        raise AppError(
            "文档文件不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )

    path = document_file_path(document.storage_path)
    if not path.exists():
        raise AppError(
            "文档文件不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )

    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document.file_name,
    )


@router.post("/{document_id}/parse", response_model=ApiResponse[DocumentResponse])
def start_document_parse(
    document_id: int,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    document = _get_document_or_404(db, document_id)
    apply_document_parse_status(document, status="parsing")
    db.commit()
    db.refresh(document)

    try:
        chunk_count = rebuild_document_text_chunks(db, document)
        apply_document_parse_status(
            document,
            status="completed",
            parse_chunk_count=chunk_count,
        )
        db.commit()
    except AppError as exc:
        db.rollback()
        db.refresh(document)
        apply_document_parse_status(
            document,
            status="failed",
            parse_progress=0,
            parse_chunk_count=0,
            parse_error_message=exc.message,
        )
        db.commit()
    except Exception as exc:
        logger.exception("Failed to parse document %s", document_id, exc_info=exc)
        db.rollback()
        db.refresh(document)
        apply_document_parse_status(
            document,
            status="failed",
            parse_progress=0,
            parse_chunk_count=0,
            parse_error_message="文档解析失败",
        )
        db.commit()

    db.refresh(document)
    return success_response(_to_document_response(document))


@router.patch("/{document_id}/status", response_model=ApiResponse[DocumentResponse])
def update_document_status(
    document_id: int,
    payload: DocumentStatusUpdate,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    document = _get_document_or_404(db, document_id)
    apply_document_parse_status(
        document,
        status=payload.status,
        parse_progress=payload.parse_progress,
        parse_chunk_count=payload.parse_chunk_count,
        parse_error_message=payload.parse_error_message,
    )
    db.commit()
    db.refresh(document)
    return success_response(_to_document_response(document))


@router.get("/{document_id}/chunks", response_model=ApiResponse[DocumentChunkListResponse])
def list_document_chunks(
    document_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(gt=0)] = 1,
    page_size: Annotated[int, Query(gt=0, le=100)] = 20,
) -> ApiResponse[DocumentChunkListResponse]:
    _get_document_or_404(db, document_id)
    offset = (page - 1) * page_size
    count_stmt = select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.document_id == document_id
    )
    total = db.scalar(count_stmt) or 0
    total_pages = (total + page_size - 1) // page_size if total else 0
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .offset(offset)
        .limit(page_size)
    ).all()

    return success_response(
        DocumentChunkListResponse(
            items=chunks,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    )


@router.delete("/{document_id}", response_model=ApiResponse[None])
def delete_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    document = _get_document_or_404(db, document_id)
    knowledge_base = document.knowledge_base
    storage_path = document.storage_path
    db.delete(document)
    knowledge_base.document_count = max(knowledge_base.document_count - 1, 0)
    db.commit()
    delete_document_file(storage_path)
    return success_response()
