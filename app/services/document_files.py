from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

SUPPORTED_DOCUMENT_FILE_TYPES = {"PDF", "DOCX", "TXT", "MD"}
_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredDocumentFile:
    original_file_name: str
    stored_file_name: str
    storage_path: str
    file_type: str
    file_size: int
    content_type: str | None


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


def storage_root() -> Path:
    root = Path(settings.document_storage_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def document_file_path(storage_path: str) -> Path:
    root = storage_root().resolve()
    path = (root / storage_path).resolve()
    if root not in path.parents and path != root:
        raise AppError(
            "文档存储路径非法",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )
    return path


def _clean_file_name(file_name: str) -> str:
    cleaned = Path(file_name).name.strip()
    if not cleaned:
        raise AppError(
            "文件名不能为空",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )
    return cleaned[:255]


def save_uploaded_document_file(
    upload_file: UploadFile,
    *,
    knowledge_base_id: int,
) -> StoredDocumentFile:
    original_file_name = _clean_file_name(upload_file.filename or "")
    file_type = normalize_document_file_type(original_file_name, "")
    extension = f".{file_type.lower()}"
    stored_file_name = f"{uuid4().hex}{extension}"
    relative_path = f"kb-{knowledge_base_id}/{stored_file_name}"
    target_path = document_file_path(relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    max_size = settings.max_document_file_size_mb * 1024 * 1024
    file_size = 0

    try:
        with target_path.open("wb") as target_file:
            while chunk := upload_file.file.read(_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > max_size:
                    raise AppError(
                        f"文档大小不能超过 {settings.max_document_file_size_mb} MB",
                        code=ErrorCode.BAD_REQUEST,
                        status_code=400,
                    )
                target_file.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    finally:
        upload_file.file.close()

    if file_size == 0:
        target_path.unlink(missing_ok=True)
        raise AppError(
            "不能上传空文档",
            code=ErrorCode.BAD_REQUEST,
            status_code=400,
        )

    return StoredDocumentFile(
        original_file_name=original_file_name,
        stored_file_name=stored_file_name,
        storage_path=relative_path,
        file_type=file_type,
        file_size=file_size,
        content_type=upload_file.content_type,
    )


def delete_document_file(storage_path: str | None) -> None:
    if not storage_path:
        return
    document_file_path(storage_path).unlink(missing_ok=True)
