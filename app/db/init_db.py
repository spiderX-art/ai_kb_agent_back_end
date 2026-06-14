from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User


def init_db() -> None:
    """创建本地开发所需表，并初始化默认登录用户。"""
    Base.metadata.create_all(bind=engine)

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
