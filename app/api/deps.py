from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(
            "未登录或登录已过期",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise AppError(
            "未登录或登录已过期",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.isdigit():
        raise AppError(
            "未登录或登录已过期",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )

    user = db.scalar(select(User).where(User.id == int(user_id)))
    if user is None:
        raise AppError(
            "未登录或登录已过期",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )

    return user


def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != "admin":
        raise AppError(
            "只有管理员可以执行该操作",
            code=ErrorCode.FORBIDDEN,
            status_code=403,
        )

    return current_user
