from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentChunkEmbedding(Base):
    """文档分片向量缓存。

    当前先使用本地确定性哈希向量打通检索链路，后续可替换为外部 Embedding 模型。
    """

    __tablename__ = "document_chunk_embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_document_chunk_embeddings_chunk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_vector: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    chunk = relationship("DocumentChunk", back_populates="embedding")
    document = relationship("Document")
    knowledge_base = relationship("KnowledgeBase")
