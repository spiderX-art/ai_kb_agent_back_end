from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.schemas.response import ApiResponse, success_response
from app.services.knowledge_bases import (
    create_knowledge_base_record,
    delete_knowledge_base_record,
    get_knowledge_base_or_404,
    list_knowledge_base_records,
    update_knowledge_base_record,
)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge_bases"])


@router.get("", response_model=ApiResponse[list[KnowledgeBaseResponse]])
def list_knowledge_bases(
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[KnowledgeBaseResponse]]:
    knowledge_bases = list_knowledge_base_records(db)
    return success_response(
        [KnowledgeBaseResponse.model_validate(item) for item in knowledge_bases]
    )


@router.post("", response_model=ApiResponse[KnowledgeBaseResponse])
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = create_knowledge_base_record(db, payload, current_user)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.get("/{knowledge_base_id}", response_model=ApiResponse[KnowledgeBaseResponse])
def get_knowledge_base(
    knowledge_base_id: int,
    _: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = get_knowledge_base_or_404(db, knowledge_base_id)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.put("/{knowledge_base_id}", response_model=ApiResponse[KnowledgeBaseResponse])
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[KnowledgeBaseResponse]:
    knowledge_base = update_knowledge_base_record(db, knowledge_base_id, payload)
    return success_response(KnowledgeBaseResponse.model_validate(knowledge_base))


@router.delete("/{knowledge_base_id}", response_model=ApiResponse[None])
def delete_knowledge_base(
    knowledge_base_id: int,
    _: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    delete_knowledge_base_record(db, knowledge_base_id)
    return success_response()
