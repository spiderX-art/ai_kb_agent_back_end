from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ChatMessageRole = Literal["user", "assistant"]


class ChatAskRequest(BaseModel):
    knowledge_base_id: int = Field(gt=0)
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = Field(default=None, gt=0)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("问题不能为空")
        return question


class ChatCitation(BaseModel):
    chunk_id: int
    document_id: int
    document_file_name: str
    file_type: str
    chunk_index: int
    page_number: int | None = None
    similarity: float
    content: str


class ChatMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: ChatMessageRole
    content: str
    citations: list[ChatCitation] = []
    created_at: datetime


class ChatAskResponse(BaseModel):
    conversation_id: int
    answer_model: str
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    citations: list[ChatCitation]


class ChatConversationResponse(BaseModel):
    id: int
    knowledge_base_id: int
    knowledge_base_name: str
    title: str
    message_count: int
    last_message_preview: str
    created_at: datetime
    updated_at: datetime


class ChatConversationListResponse(BaseModel):
    items: list[ChatConversationResponse]
    total: int


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
