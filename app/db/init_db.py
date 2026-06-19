from sqlalchemy import inspect, select, text

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User


def _ensure_document_columns() -> None:
    """本地开发使用 create_all；这里补齐旧 SQLite 表缺失的新列。"""

    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("documents")}
    required_columns = {
        "storage_path": "VARCHAR(512)",
        "stored_file_name": "VARCHAR(255)",
        "content_type": "VARCHAR(128)",
        "parse_progress": "INTEGER NOT NULL DEFAULT 0",
        "parse_chunk_count": "INTEGER NOT NULL DEFAULT 0",
        "parse_error_message": "TEXT",
        "parse_started_at": "DATETIME",
        "parse_finished_at": "DATETIME",
    }

    missing_columns = {
        name: column_type
        for name, column_type in required_columns.items()
        if name not in existing_columns
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for name, column_type in missing_columns.items():
            connection.execute(
                text(f"ALTER TABLE documents ADD COLUMN {name} {column_type}")
            )


def init_db() -> None:
    """创建本地开发所需表，并初始化默认登录用户。"""
    Base.metadata.create_all(bind=engine)
    _ensure_document_columns()

    with SessionLocal() as db:
        default_users = [
            (
                settings.default_admin_username,
                settings.default_admin_password,
                settings.default_admin_role,
            ),
            (
                settings.default_username,
                settings.default_password,
                settings.default_user_role,
            ),
        ]

        has_created_user = False
        for username, password, role in default_users:
            existing_user = db.scalar(select(User).where(User.username == username))
            if existing_user is not None:
                continue

            db.add(
                User(
                    username=username,
                    password_hash=hash_password(password),
                    role=role,
                )
            )
            has_created_user = True

        if has_created_user:
            db.commit()
