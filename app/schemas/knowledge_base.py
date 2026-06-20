from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class KnowledgeBaseBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("知识库名称不能为空")
        return name

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        return value.strip()


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("知识库名称不能为空")
        return name

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class KnowledgeBaseResponse(BaseModel):
    id: int
    name: str
    description: str
    document_count: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
    }


class KnowledgeBaseSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("搜索内容不能为空")
        return query


class KnowledgeBaseSearchResult(BaseModel):
    chunk_id: int
    document_id: int
    document_file_name: str
    file_type: str
    chunk_index: int
    content: str
    content_length: int
    page_number: int | None = None
    similarity: float


class KnowledgeBaseSearchResponse(BaseModel):
    query: str
    embedding_model: str
    total: int
    items: list[KnowledgeBaseSearchResult]
