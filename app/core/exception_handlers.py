import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorCode
from app.schemas.response import ApiResponse

logger = logging.getLogger(__name__)


def _json_error_response(
    *,
    status_code: int,
    code: ErrorCode | int,
    message: str,
    data: Any | None = None,
) -> JSONResponse:
    body = ApiResponse[Any](
        code=int(code),
        message=message,
        data=data,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return _json_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        data=exc.data,
    )


async def http_exception_handler(
    _: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if exc.status_code == 404:
        code = ErrorCode.NOT_FOUND
        message = "资源不存在"
    elif exc.status_code == 401:
        code = ErrorCode.UNAUTHORIZED
        message = "未登录或登录已过期"
    elif exc.status_code == 403:
        code = ErrorCode.FORBIDDEN
        message = "没有权限访问该资源"
    else:
        code = ErrorCode.BAD_REQUEST
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"

    return _json_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
    )


async def validation_exception_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "loc": error.get("loc", ()),
            "message": error.get("msg", "字段校验失败"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return _json_error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR,
        message="请求参数校验失败",
        data={"errors": errors},
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return _json_error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR,
        message="服务器内部错误",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
