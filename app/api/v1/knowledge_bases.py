from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models import KnowledgeBase, User
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.schemas.response import ApiResponse, success_response

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge_bases"])


def _get_knowledge_base_or_404(db: Session, knowledge_base_id: int) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        raise AppError(
            "知识库不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return knowledge_base


def _ensure_name_available(
    db: Session,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    stmt = select(KnowledgeBase).where(KnowledgeBase.name == name)
    if exclude_id is not None:
        stmt = stmt.where(KnowledgeBase.id != exclude_id)

    if db.scalar(stmt) is not None:
        raise AppError(
            "知识库名称已存在",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )


@router.get("", response_model=ApiResponse[list[KnowledgeBaseResponse]])
def list_knowledge_bases(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[KnowledgeBaseResponse]]:
    knowledge_bases = db.scalars(
        select(KnowledgeBase).order_by(
            KnowledgeBase.updated_at.desc(),
            KnowledgeBase.id.desc(),
        )
    ).all()
    return success_response(
        [KnowledgeBaseResponse.model_validate(item) for item in knowledge_bases]
    )


@router.post("", response_model=ApiResponse[KnowledgeBaseResponse])
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    _ensure_name_available(db, payload.name)

    knowledge_base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        created_by_id=current_user.id,
    )
    db.add(knowledge_base)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "知识库名称已存在",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        ) from exc

    db.refresh(knowledge_base)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.get("/{knowledge_base_id}", response_model=ApiResponse[KnowledgeBaseResponse])
def get_knowledge_base(
    knowledge_base_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = _get_knowledge_base_or_404(db, knowledge_base_id)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.put("/{knowledge_base_id}", response_model=ApiResponse[KnowledgeBaseResponse])
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = _get_knowledge_base_or_404(db, knowledge_base_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise AppError(
            "请至少提交一个需要更新的字段",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    if "name" in update_data:
        _ensure_name_available(db, update_data["name"], exclude_id=knowledge_base.id)
        knowledge_base.name = update_data["name"]

    if "description" in update_data:
        knowledge_base.description = update_data["description"]

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "知识库名称已存在",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        ) from exc

    db.refresh(knowledge_base)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.delete("/{knowledge_base_id}", response_model=ApiResponse[None])
def delete_knowledge_base(
    knowledge_base_id: int,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    knowledge_base = _get_knowledge_base_or_404(db, knowledge_base_id)
    db.delete(knowledge_base)
    db.commit()
    return success_response()
