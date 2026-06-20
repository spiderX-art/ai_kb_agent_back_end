from dataclasses import dataclass
from datetime import UTC, datetime
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models import ChatConversation, ChatMessage, KnowledgeBase, User
from app.schemas.chat import (
    ChatAskRequest,
    ChatCitation,
    ChatConversationResponse,
    ChatMessageResponse,
)
from app.services.document_embeddings import (
    KnowledgeBaseSearchHit,
    ensure_knowledge_base_chunk_embeddings,
    search_knowledge_base_chunks,
)
from app.services.knowledge_bases import get_knowledge_base_or_404

CHAT_ANSWER_MODEL_NAME = "local-rag-extractive-v1"
_MAX_TITLE_LENGTH = 48
_MAX_PREVIEW_LENGTH = 80
_MAX_CITATION_CONTENT_LENGTH = 1000
_MAX_ANSWER_EXCERPT_LENGTH = 420


@dataclass(frozen=True)
class ChatAskResult:
    conversation: ChatConversation
    user_message: ChatMessage
    assistant_message: ChatMessage
    citations: list[ChatCitation]


def _now() -> datetime:
    return datetime.now(UTC)


def _compact_text(text: str, max_length: int) -> str:
    compacted = " ".join(text.strip().split())
    if len(compacted) <= max_length:
        return compacted
    return f"{compacted[: max_length - 1]}..."


def _conversation_title(question: str) -> str:
    return _compact_text(question, _MAX_TITLE_LENGTH)


def _message_preview(content: str) -> str:
    return _compact_text(content, _MAX_PREVIEW_LENGTH)


def _citation_from_hit(hit: KnowledgeBaseSearchHit) -> ChatCitation:
    return ChatCitation(
        chunk_id=hit.chunk.id,
        document_id=hit.document.id,
        document_file_name=hit.document.file_name,
        file_type=hit.document.file_type,
        chunk_index=hit.chunk.chunk_index,
        page_number=hit.chunk.page_number,
        similarity=round(hit.similarity, 4),
        content=_compact_text(hit.chunk.content, _MAX_CITATION_CONTENT_LENGTH),
    )


def _encode_citations(citations: list[ChatCitation]) -> str | None:
    if not citations:
        return None
    return json.dumps(
        [citation.model_dump() for citation in citations],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_citations(value: str | None) -> list[ChatCitation]:
    if not value:
        return []

    try:
        raw_citations = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(raw_citations, list):
        return []

    citations: list[ChatCitation] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            continue
        try:
            citations.append(ChatCitation.model_validate(item))
        except ValueError:
            continue
    return citations


def message_to_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        citations=_decode_citations(message.citations_json),
        created_at=message.created_at,
    )


def _build_answer(question: str, citations: list[ChatCitation]) -> str:
    if not citations:
        return (
            "我没有在当前知识库中检索到足够相关的已解析文档内容，"
            "暂时无法基于知识库回答这个问题。请换一个问法，或先上传并解析相关文档。"
        )

    lines = [
        f"基于当前知识库中与「{question}」最相关的内容，我整理到以下依据：",
    ]
    for index, citation in enumerate(citations, start=1):
        page_text = f"，第 {citation.page_number} 页" if citation.page_number else ""
        excerpt = _compact_text(citation.content, _MAX_ANSWER_EXCERPT_LENGTH)
        lines.append(
            f"{index}. {excerpt}（来源：{citation.document_file_name}{page_text}）"
        )

    lines.append("当前版本使用本地检索结果生成回答，正式大模型接入后会在这些引用基础上做进一步归纳。")
    return "\n\n".join(lines)


def _get_user_conversation_or_404(
    db: Session,
    *,
    conversation_id: int,
    current_user: User,
) -> ChatConversation:
    conversation = db.get(ChatConversation, conversation_id)
    if conversation is None or conversation.created_by_id != current_user.id:
        raise AppError(
            "会话不存在",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )
    return conversation


def ask_chat_question(
    db: Session,
    *,
    payload: ChatAskRequest,
    current_user: User,
) -> ChatAskResult:
    knowledge_base = get_knowledge_base_or_404(db, payload.knowledge_base_id)
    conversation: ChatConversation
    if payload.conversation_id:
        conversation = _get_user_conversation_or_404(
            db,
            conversation_id=payload.conversation_id,
            current_user=current_user,
        )
        if conversation.knowledge_base_id != knowledge_base.id:
            raise AppError(
                "当前会话不属于所选知识库",
                code=ErrorCode.BAD_REQUEST,
                status_code=400,
            )
    else:
        conversation = ChatConversation(
            knowledge_base_id=knowledge_base.id,
            title=_conversation_title(payload.question),
            created_by_id=current_user.id,
        )
        db.add(conversation)
        db.flush()

    ensure_knowledge_base_chunk_embeddings(db, knowledge_base.id)
    hits = search_knowledge_base_chunks(
        db,
        knowledge_base_id=knowledge_base.id,
        query=payload.question,
        limit=payload.top_k,
    )
    citations = [_citation_from_hit(hit) for hit in hits]
    answer = _build_answer(payload.question, citations)
    timestamp = _now()

    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.question,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations_json=_encode_citations(citations),
    )
    conversation.updated_at = timestamp
    db.add_all([user_message, assistant_message])
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)
    db.refresh(assistant_message)

    return ChatAskResult(
        conversation=conversation,
        user_message=user_message,
        assistant_message=assistant_message,
        citations=citations,
    )


def list_user_chat_conversations(
    db: Session,
    *,
    current_user: User,
    limit: int,
) -> list[ChatConversationResponse]:
    rows = db.execute(
        select(ChatConversation, KnowledgeBase)
        .join(KnowledgeBase, ChatConversation.knowledge_base_id == KnowledgeBase.id)
        .where(ChatConversation.created_by_id == current_user.id)
        .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        .limit(limit)
    ).all()

    responses: list[ChatConversationResponse] = []
    for conversation, knowledge_base in rows:
        messages = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        ).all()
        last_message = messages[-1].content if messages else ""
        responses.append(
            ChatConversationResponse(
                id=conversation.id,
                knowledge_base_id=conversation.knowledge_base_id,
                knowledge_base_name=knowledge_base.name,
                title=conversation.title,
                message_count=len(messages),
                last_message_preview=_message_preview(last_message),
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
    return responses


def list_user_chat_messages(
    db: Session,
    *,
    conversation_id: int,
    current_user: User,
) -> list[ChatMessageResponse]:
    _get_user_conversation_or_404(
        db,
        conversation_id=conversation_id,
        current_user=current_user,
    )
    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    ).all()
    return [message_to_response(message) for message in messages]


def count_user_chat_conversations(db: Session, *, current_user: User) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ChatConversation)
            .where(ChatConversation.created_by_id == current_user.id)
        )
        or 0
    )
