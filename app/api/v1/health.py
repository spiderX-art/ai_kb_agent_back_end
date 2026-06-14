from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.schemas.response import ApiResponse, success_response

router = APIRouter(tags=["health"])


class HealthData(BaseModel):
    status: str
    service: str
    version: str


class DatabaseHealthData(BaseModel):
    status: str
    result: int


@router.get(
    "/health",
    response_model=ApiResponse[HealthData],
    summary="服务健康检查",
)
async def health_check() -> ApiResponse[HealthData]:
    """给部署平台和前端联调用，用来确认后端服务已经正常启动。"""
    return success_response(
        HealthData(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
        )
    )


@router.get(
    "/health/db",
    response_model=ApiResponse[DatabaseHealthData],
    summary="数据库连接健康检查",
)
def database_health_check(db: Session = Depends(get_db)) -> ApiResponse[DatabaseHealthData]:
    """执行最简单的 SQL，确认应用能连上数据库。"""
    try:
        result = db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError as exc:
        raise AppError(
            "数据库连接失败",
            code=ErrorCode.DATABASE_ERROR,
            status_code=503,
        ) from exc

    return success_response(
        DatabaseHealthData(
            status="ok",
            result=int(result),
        )
    )
