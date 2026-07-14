from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.knowledge_bases import router as knowledge_bases_router
from app.api.v1.endpoints.documents import kb_documents_router, documents_router
from app.api.v1.endpoints.tools import router as tools_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(agents_router)
api_router.include_router(conversations_router)
api_router.include_router(knowledge_bases_router)
api_router.include_router(kb_documents_router)
api_router.include_router(documents_router)
api_router.include_router(tools_router)
