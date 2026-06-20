from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
import re

from app.core.errors import AppError, ErrorCode
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.services.document_files import document_file_path

PARSABLE_DOCUMENT_FILE_TYPES = {"PDF", "TXT", "MD"}
TEXT_DOCUMENT_FILE_TYPES = {"TXT", "MD"}
_ALLOWED_STATUS_TRANSITIONS = {
    "uploaded": {"parsing"},
    "parsing": {"parsing", "completed", "failed"},
    "failed": {"parsing"},
    "completed": {"parsing"},
}
_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1")
_CHUNK_TARGET_SIZE = 1000
_CHUNK_OVERLAP = 120
_MIN_BREAK_POSITION = int(_CHUNK_TARGET_SIZE * 0.6)
_BREAK_CHARS = ("\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " ")


@dataclass(frozen=True)
class ExtractedTextSection:
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class ParsedTextChunk:
    content: str
    page_number: int | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_document_is_parseable(document: Document) -> None:
    if document.file_type not in PARSABLE_DOCUMENT_FILE_TYPES:
        raise AppError(
            "暂仅支持 PDF、TXT、MD 文档解析",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    if not document.storage_path:
        raise AppError(
            "请先上传文档文件后再发起解析",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    if not document_file_path(document.storage_path).exists():
        raise AppError(
            "文档文件不存在，无法发起解析",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
        )


def _normalize_extracted_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _read_text_file(path: Path) -> str:
    raw_content = path.read_bytes()
    for encoding in _TEXT_ENCODINGS:
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_content.decode("utf-8", errors="replace")


def _extract_pdf_sections(path: Path) -> list[ExtractedTextSection]:
    try:
        import fitz
    except ImportError as exc:
        raise AppError(
            "后端缺少 PyMuPDF 依赖，无法解析 PDF",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
        ) from exc

    try:
        pdf = fitz.open(str(path))
    except Exception as exc:
        raise AppError(
            "PDF 文档打开失败",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        ) from exc

    with pdf:
        if pdf.needs_pass:
            raise AppError(
                "暂不支持解析加密 PDF",
                code=ErrorCode.BAD_REQUEST,
                status_code=400,
            )

        sections: list[ExtractedTextSection] = []
        for page_index in range(pdf.page_count):
            page = pdf.load_page(page_index)
            text = _normalize_extracted_text(page.get_text("text"))
            if text:
                sections.append(
                    ExtractedTextSection(
                        text=text,
                        page_number=page_index + 1,
                    )
                )
        return sections


def _extract_document_sections(document: Document) -> list[ExtractedTextSection]:
    _ensure_document_is_parseable(document)
    path = document_file_path(document.storage_path or "")

    if document.file_type in TEXT_DOCUMENT_FILE_TYPES:
        text = _normalize_extracted_text(_read_text_file(path))
        return [ExtractedTextSection(text=text)] if text else []

    if document.file_type == "PDF":
        return _extract_pdf_sections(path)

    raise AppError(
        "暂仅支持 PDF、TXT、MD 文档解析",
        code=ErrorCode.BAD_REQUEST,
        status_code=400,
    )


def _find_break_position(text: str, start: int, end: int) -> int:
    window = text[start:end]
    break_position = -1
    for char in _BREAK_CHARS:
        break_position = max(break_position, window.rfind(char))

    if break_position >= _MIN_BREAK_POSITION:
        return start + break_position + 1
    return end


def _split_long_text(text: str, page_number: int | None) -> list[ParsedTextChunk]:
    chunks: list[ParsedTextChunk] = []
    start = 0

    while start < len(text):
        end = min(start + _CHUNK_TARGET_SIZE, len(text))
        if end < len(text):
            end = _find_break_position(text, start, end)

        content = text[start:end].strip()
        if content:
            chunks.append(ParsedTextChunk(content=content, page_number=page_number))

        if end >= len(text):
            break

        start = max(end - _CHUNK_OVERLAP, start + 1)

    return chunks


def _split_section_into_chunks(section: ExtractedTextSection) -> list[ParsedTextChunk]:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", section.text)
        if paragraph.strip()
    ]
    chunks: list[ParsedTextChunk] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        content = current.strip()
        if content:
            chunks.append(
                ParsedTextChunk(content=content, page_number=section.page_number)
            )
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > _CHUNK_TARGET_SIZE:
            flush_current()
            chunks.extend(_split_long_text(paragraph, section.page_number))
            continue

        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= _CHUNK_TARGET_SIZE:
            current = candidate
        else:
            flush_current()
            current = paragraph

    flush_current()
    return chunks


def parse_document_text_chunks(document: Document) -> list[ParsedTextChunk]:
    sections = _extract_document_sections(document)
    chunks: list[ParsedTextChunk] = []
    for section in sections:
        chunks.extend(_split_section_into_chunks(section))

    if not chunks:
        raise AppError(
            "未从文档中提取到可用文本内容",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    return chunks


def rebuild_document_text_chunks(db: Session, document: Document) -> int:
    chunks = parse_document_text_chunks(document)
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    db.add_all(
        DocumentChunk(
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            chunk_index=index,
            content=chunk.content,
            content_length=len(chunk.content),
            page_number=chunk.page_number,
        )
        for index, chunk in enumerate(chunks)
    )
    return len(chunks)


def _validate_transition(current_status: str, next_status: str) -> None:
    if next_status == "uploaded":
        raise AppError(
            "解析任务不能回退到已上传状态",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    if next_status not in _ALLOWED_STATUS_TRANSITIONS.get(current_status, set()):
        raise AppError(
            f"不支持从 {current_status} 流转到 {next_status}",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )


def apply_document_parse_status(
    document: Document,
    *,
    status: str,
    parse_progress: int | None = None,
    parse_chunk_count: int | None = None,
    parse_error_message: str | None = None,
) -> None:
    _validate_transition(document.status, status)

    if status == "parsing":
        _ensure_document_is_parseable(document)
        if document.status != "parsing":
            document.parse_started_at = _now()
            document.parse_finished_at = None
            document.parse_error_message = None
            document.parse_progress = 0
            document.parse_chunk_count = 0

        if parse_progress is not None:
            document.parse_progress = parse_progress
        if parse_chunk_count is not None:
            document.parse_chunk_count = parse_chunk_count
        document.status = "parsing"
        return

    if status == "completed":
        document.status = "completed"
        document.parse_progress = 100
        if parse_chunk_count is not None:
            document.parse_chunk_count = parse_chunk_count
        document.parse_error_message = None
        document.parse_finished_at = _now()
        return

    if status == "failed":
        document.status = "failed"
        if parse_progress is not None:
            document.parse_progress = parse_progress
        if parse_chunk_count is not None:
            document.parse_chunk_count = parse_chunk_count
        document.parse_error_message = parse_error_message or "解析失败"
        document.parse_finished_at = _now()
        return

    raise AppError(
        "未知解析状态",
        code=ErrorCode.BAD_REQUEST,
        status_code=400,
    )
