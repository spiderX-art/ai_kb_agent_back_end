from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    把应用创建逻辑放进函数里，后续写测试时可以复用这个函数创建测试应用。
    """

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )

    # CORS 允许本地前端开发服务器访问后端 API。
    # 生产环境应把这里收窄到正式前端域名。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 所有 v1 接口都会统一挂到 /api/v1 下。
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    register_exception_handlers(app)

    return app


app = create_app()
