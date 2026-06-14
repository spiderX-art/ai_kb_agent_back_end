from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。

    BaseSettings 会自动从环境变量读取值。
    例如 Python 字段 app_name 会读取环境变量 APP_NAME。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI KB Agent API"
    app_version: str = "0.1.0"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    database_url: str = "sqlite:///./app.db"
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24
    default_admin_username: str = "admin"
    default_admin_password: str = "123456"
    default_admin_role: str = "admin"
    default_username: str = "user"
    default_password: str = "123456"
    default_user_role: str = "user"

    # 先放配置入口，后续接入 OpenAI 时会从这里读取。
    openai_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，避免每次请求都重新读取 .env 文件。"""
    return Settings()


settings = get_settings()
