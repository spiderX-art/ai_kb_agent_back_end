from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk, DocumentChunkEmbedding

EMBEDDING_MODEL_NAME = "local-hash-v1"
EMBEDDING_DIMENSION = 256
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


@dataclass(frozen=True)
class KnowledgeBaseSearchHit:
    chunk: DocumentChunk
    document: Document
    similarity: float


def _is_cjk_text(value: str) -> bool:
    return all("\u4e00" <= char <= "\u9fff" for char in value)


def _tokenize_text(text: str) -> list[str]:
    normalized = text.lower()
    tokens: list[str] = []

    for match in _TOKEN_PATTERN.findall(normalized):
        if _is_cjk_text(match):
            tokens.extend(match)
            tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
            continue

        tokens.append(match)
        if len(match) >= 6:
            tokens.extend(match[index : index + 4] for index in range(len(match) - 3))

    return tokens


def _hash_token(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_text(text: str) -> list[float]:
    """生成本地确定性文本向量。

    这是一个轻量检索占位实现，不需要外部模型服务；后续接入正式 Embedding 时只需替换本服务。
    """

    token_counts = Counter(_tokenize_text(text))
    vector = [0.0] * EMBEDDING_DIMENSION

    for token, count in token_counts.items():
        index = _hash_token(token) % EMBEDDING_DIMENSION
        vector[index] += float(count)

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


def _encode_embedding(vector: list[float]) -> str:
    compact_vector = [round(value, 6) for value in vector]
    return json.dumps(compact_vector, separators=(",", ":"))


def _decode_embedding(value: str) -> list[float]:
    try:
        vector = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(vector, list):
        return []

    return [float(item) for item in vector if isinstance(item, (int, float))]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def _build_embedding(chunk: DocumentChunk) -> DocumentChunkEmbedding:
    if chunk.id is None:
        raise ValueError("文档分片保存后才能生成向量")

    return DocumentChunkEmbedding(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        knowledge_base_id=chunk.knowledge_base_id,
        embedding_model=EMBEDDING_MODEL_NAME,
        embedding_dimension=EMBEDDING_DIMENSION,
        embedding_vector=_encode_embedding(embed_text(chunk.content)),
        content_hash=_content_hash(chunk.content),
    )


def rebuild_document_chunk_embeddings(db: Session, document_id: int) -> int:
    db.execute(
        delete(DocumentChunkEmbedding).where(
            DocumentChunkEmbedding.document_id == document_id
        )
    )
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
    ).all()
    db.add_all(_build_embedding(chunk) for chunk in chunks)
    db.flush()
    return len(chunks)


def ensure_knowledge_base_chunk_embeddings(
    db: Session,
    knowledge_base_id: int,
) -> int:
    """补齐或刷新知识库下缺失/过期的分片向量，返回变更数量。"""

    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.knowledge_base_id == knowledge_base_id)
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
    ).all()
    changed_count = 0

    for chunk in chunks:
        expected_hash = _content_hash(chunk.content)
        existing = db.scalar(
            select(DocumentChunkEmbedding).where(
                DocumentChunkEmbedding.chunk_id == chunk.id
            )
        )
        if (
            existing is not None
            and existing.embedding_model == EMBEDDING_MODEL_NAME
            and existing.embedding_dimension == EMBEDDING_DIMENSION
            and existing.content_hash == expected_hash
        ):
            continue

        embedding = _build_embedding(chunk)
        if existing is None:
            db.add(embedding)
        else:
            existing.document_id = embedding.document_id
            existing.knowledge_base_id = embedding.knowledge_base_id
            existing.embedding_model = embedding.embedding_model
            existing.embedding_dimension = embedding.embedding_dimension
            existing.embedding_vector = embedding.embedding_vector
            existing.content_hash = embedding.content_hash
        changed_count += 1

    if changed_count:
        db.flush()

    return changed_count


def search_knowledge_base_chunks(
    db: Session,
    *,
    knowledge_base_id: int,
    query: str,
    limit: int,
) -> list[KnowledgeBaseSearchHit]:
    query_vector = embed_text(query)
    if not any(query_vector):
        return []

    rows = db.execute(
        select(DocumentChunkEmbedding, DocumentChunk, Document)
        .join(DocumentChunk, DocumentChunkEmbedding.chunk_id == DocumentChunk.id)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunkEmbedding.knowledge_base_id == knowledge_base_id,
            Document.status == "completed",
        )
    ).all()

    hits: list[KnowledgeBaseSearchHit] = []
    for embedding, chunk, document in rows:
        similarity = _cosine_similarity(
            query_vector,
            _decode_embedding(embedding.embedding_vector),
        )
        if similarity <= 0:
            continue

        hits.append(
            KnowledgeBaseSearchHit(
                chunk=chunk,
                document=document,
                similarity=similarity,
            )
        )

    return sorted(hits, key=lambda item: item.similarity, reverse=True)[:limit]
