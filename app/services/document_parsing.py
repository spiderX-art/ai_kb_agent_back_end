from datetime import UTC, datetime

from app.core.errors import AppError, ErrorCode
from app.models import Document
from app.services.document_files import document_file_path

PARSABLE_DOCUMENT_FILE_TYPES = {"PDF", "TXT", "MD"}
_ALLOWED_STATUS_TRANSITIONS = {
    "uploaded": {"parsing"},
    "parsing": {"parsing", "completed", "failed"},
    "failed": {"parsing"},
    "completed": set(),
}


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
