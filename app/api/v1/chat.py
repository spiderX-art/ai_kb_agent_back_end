from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.chat import (
    ChatAskRequest,
    ChatAskResponse,
    ChatConversationListResponse,
    ChatMessageListResponse,
)
from app.schemas.response import ApiResponse, success_response
from app.services.chat import (
    CHAT_ANSWER_MODEL_NAME,
    ask_chat_question,
    count_user_chat_conversations,
    list_user_chat_conversations,
    list_user_chat_messages,
    message_to_response,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/messages", response_model=ApiResponse[ChatAskResponse])
def create_chat_message(
    payload: ChatAskRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ChatAskResponse]:
    result = ask_chat_question(db, payload=payload, current_user=current_user)
    return success_response(
        ChatAskResponse(
            conversation_id=result.conversation.id,
            answer_model=CHAT_ANSWER_MODEL_NAME,
            user_message=message_to_response(result.user_message),
            assistant_message=message_to_response(result.assistant_message),
            citations=result.citations,
        )
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[ChatConversationListResponse],
)
def list_chat_conversations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(gt=0, le=100)] = 30,
) -> ApiResponse[ChatConversationListResponse]:
    conversations = list_user_chat_conversations(
        db,
        current_user=current_user,
        limit=limit,
    )
    return success_response(
        ChatConversationListResponse(
            items=conversations,
            total=count_user_chat_conversations(db, current_user=current_user),
        )
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[ChatMessageListResponse],
)
def list_chat_conversation_messages(
    conversation_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[ChatMessageListResponse]:
    messages = list_user_chat_messages(
        db,
        conversation_id=conversation_id,
        current_user=current_user,
    )
    return success_response(
        ChatMessageListResponse(
            items=messages,
            total=len(messages),
        )
    )
