from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    BAD_REQUEST = 40000
    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    VALIDATION_ERROR = 42200
    INTERNAL_ERROR = 50000
    DATABASE_ERROR = 50010


class AppError(Exception):
    """业务异常。

    接口里主动 raise AppError，统一异常处理器会把它转换成固定 JSON 结构。
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | int = ErrorCode.BAD_REQUEST,
        status_code: int = 400,
        data: Any | None = None,
    ) -> None:
        self.message = message
        self.code = int(code)
        self.status_code = status_code
        self.data = data
        super().__init__(message)
