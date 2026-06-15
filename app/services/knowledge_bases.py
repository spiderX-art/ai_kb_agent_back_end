from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models import KnowledgeBase, User
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate


def get_knowledge_base_or_404(db: Session, knowledge_base_id: int) -> KnowledgeBase:
    """接口层复用的知识库存在性校验。"""

    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        raise AppError(
            "知识库不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return knowledge_base


def ensure_knowledge_base_name_available(
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


def list_knowledge_base_records(db: Session) -> list[KnowledgeBase]:
    return db.scalars(
        select(KnowledgeBase).order_by(
            KnowledgeBase.updated_at.desc(),
            KnowledgeBase.id.desc(),
        )
    ).all()


def _commit_or_name_conflict(db: Session) -> None:
    """数据库唯一约束是最后防线，避免并发创建/更新绕过提前校验。"""

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "知识库名称已存在",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        ) from exc


def create_knowledge_base_record(
    db: Session,
    payload: KnowledgeBaseCreate,
    current_user: User,
) -> KnowledgeBase:
    ensure_knowledge_base_name_available(db, payload.name)

    knowledge_base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        created_by_id=current_user.id,
    )
    db.add(knowledge_base)
    _commit_or_name_conflict(db)
    db.refresh(knowledge_base)
    return knowledge_base


def update_knowledge_base_record(
    db: Session,
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
) -> KnowledgeBase:
    knowledge_base = get_knowledge_base_or_404(db, knowledge_base_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise AppError(
            "请至少提交一个需要更新的字段",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    if "name" in update_data:
        ensure_knowledge_base_name_available(
            db,
            update_data["name"],
            exclude_id=knowledge_base.id,
        )
        knowledge_base.name = update_data["name"]

    if "description" in update_data:
        knowledge_base.description = update_data["description"]

    _commit_or_name_conflict(db)
    db.refresh(knowledge_base)
    return knowledge_base


def delete_knowledge_base_record(db: Session, knowledge_base_id: int) -> None:
    knowledge_base = get_knowledge_base_or_404(db, knowledge_base_id)
    db.delete(knowledge_base)
    db.commit()
