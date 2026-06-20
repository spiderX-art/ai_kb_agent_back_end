from fastapi import APIRouter

from app.api.v1 import auth, chat, documents, health, knowledge_bases

# api_router 是 v1 版本接口的统一入口。
# 后续 auth、knowledge_bases、documents、chat 等模块都会在这里注册。
api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
