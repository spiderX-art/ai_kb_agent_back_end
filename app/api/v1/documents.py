from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models import Document, User
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentStatus,
    DocumentStatusUpdate,
)
from app.schemas.response import ApiResponse, success_response
from app.services.document_files import normalize_document_file_type
from app.services.knowledge_bases import get_knowledge_base_or_404

router = APIRouter(prefix="/documents", tags=["documents"])


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
        status=document.status,
        created_by_id=document.created_by_id,
        uploaded_at=document.uploaded_at,
        updated_at=document.updated_at,
    )


@router.get("", response_model=ApiResponse[list[DocumentResponse]])
def list_documents(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    knowledge_base_id: Annotated[int | None, Query(gt=0)] = None,
    status: DocumentStatus | None = None,
    file_type: str | None = None,
    keyword: str | None = None,
) -> ApiResponse[list[DocumentResponse]]:
    stmt = select(Document).join(Document.knowledge_base)

    if knowledge_base_id is not None:
        stmt = stmt.where(Document.knowledge_base_id == knowledge_base_id)

    if status is not None:
        stmt = stmt.where(Document.status == status)

    if file_type:
        stmt = stmt.where(Document.file_type == file_type.strip().lstrip(".").upper())

    if keyword:
        stmt = stmt.where(Document.file_name.contains(keyword.strip()))

    documents = db.scalars(
        stmt.order_by(
            Document.created_at.desc(),
            Document.id.desc(),
        )
    ).all()
    return success_response([_to_document_response(item) for item in documents])


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


@router.get("/{document_id}", response_model=ApiResponse[DocumentResponse])
def get_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    document = _get_document_or_404(db, document_id)
    return success_response(_to_document_response(document))


@router.patch("/{document_id}/status", response_model=ApiResponse[DocumentResponse])
def update_document_status(
    document_id: int,
    payload: DocumentStatusUpdate,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DocumentResponse]:
    document = _get_document_or_404(db, document_id)
    document.status = payload.status
    db.commit()
    db.refresh(document)
    return success_response(_to_document_response(document))


@router.delete("/{document_id}", response_model=ApiResponse[None])
def delete_document(
    document_id: int,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    document = _get_document_or_404(db, document_id)
    knowledge_base = document.knowledge_base
    db.delete(document)
    knowledge_base.document_count = max(knowledge_base.document_count - 1, 0)
    db.commit()
    return success_response()
