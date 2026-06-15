from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocumentStatus = Literal["uploaded", "parsing", "completed", "failed"]


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


class DocumentResponse(BaseModel):
    id: int
    knowledge_base_id: int
    knowledge_base_name: str
    file_name: str
    file_type: str
    file_size: int
    status: str
    created_by_id: int
    uploaded_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }
