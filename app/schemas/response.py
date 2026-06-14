from typing import Generic, TypeVar

from pydantic import BaseModel


DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """统一 API 响应结构。

    成功时 code 为 0；失败时 code 使用业务错误码，HTTP 状态码仍表达请求结果。
    """

    code: int = 0
    message: str = "ok"
    data: DataT | None = None


def success_response(
    data: DataT | None = None,
    message: str = "ok",
) -> ApiResponse[DataT]:
    return ApiResponse[DataT](
        code=0,
        message=message,
        data=data,
    )
