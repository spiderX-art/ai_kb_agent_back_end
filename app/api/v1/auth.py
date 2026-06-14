from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, UserProfile
from app.schemas.response import ApiResponse, success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[LoginResponse]:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError(
            "用户名或密码错误",
            code=ErrorCode.UNAUTHORIZED,
            status_code=401,
        )

    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        subject=str(user.id),
        expires_delta=expires_delta,
        extra_claims={"username": user.username, "role": user.role},
    )
    return success_response(
        LoginResponse(
            access_token=access_token,
            expires_in=int(expires_delta.total_seconds()),
            user=UserProfile.model_validate(user),
        )
    )


@router.post("/logout", response_model=ApiResponse[None])
def logout(
    _: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[None]:
    return success_response()


@router.get("/profile", response_model=ApiResponse[UserProfile])
def profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[UserProfile]:
    return success_response(UserProfile.model_validate(current_user))
