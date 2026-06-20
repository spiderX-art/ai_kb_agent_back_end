from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocumentStatus = Literal["uploaded", "parsing", "completed", "failed"]
DocumentListSortBy = Literal[
    "uploaded_at",
    "file_name",
    "file_type",
    "status",
    "knowledge_base_name",
]
SortOrder = Literal["asc", "desc"]


class DocumentCreate(BaseModel):
    knowledge_base_id: int = Field(gt=0)
    file_name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(default="", max_length=32)
    file_size: int = Field(default=0, ge=0)

    @field_validator("file_name")
    @classmethod
    def strip_file_name(cls, value: str) -> str:
        file_name = value.strip()
        if not file_name:
            raise ValueError("文件名不能为空")
        return file_name

    @field_validator("file_type")
    @classmethod
    def normalize_file_type(cls, value: str) -> str:
        return value.strip().lstrip(".").upper()


class DocumentStatusUpdate(BaseModel):
    status: DocumentStatus
    parse_progress: int | None = Field(default=None, ge=0, le=100)
    parse_chunk_count: int | None = Field(default=None, ge=0)
    parse_error_message: str | None = Field(default=None, max_length=1000)

    @field_validator("parse_error_message")
    @classmethod
    def strip_parse_error_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        message = value.strip()
        return message or None


class DocumentResponse(BaseModel):
    id: int
    knowledge_base_id: int
    knowledge_base_name: str
    file_name: str
    file_type: str
    file_size: int
    has_file: bool = False
    status: str
    parse_progress: int
    parse_chunk_count: int
    parse_error_message: str | None = None
    parse_started_at: datetime | None = None
    parse_finished_at: datetime | None = None
    created_by_id: int
    uploaded_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    knowledge_base_id: int
    chunk_index: int
    content: str
    content_length: int
    page_number: int | None = None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
