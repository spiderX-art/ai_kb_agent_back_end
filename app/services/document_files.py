from pathlib import Path

from app.core.errors import AppError, ErrorCode

SUPPORTED_DOCUMENT_FILE_TYPES = {"PDF", "DOCX", "TXT", "MD"}


def infer_document_file_type(file_name: str) -> str:
    return Path(file_name).suffix.lstrip(".").upper()


def normalize_document_file_type(file_name: str, file_type: str) -> str:
    """统一文档类型入口，避免上传、解析、列表过滤各自维护格式规则。"""

    normalized_type = file_type or infer_document_file_type(file_name)
    if normalized_type not in SUPPORTED_DOCUMENT_FILE_TYPES:
        raise AppError(
            "暂仅支持 PDF、DOCX、TXT、MD 格式文档",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )
    return normalized_type
