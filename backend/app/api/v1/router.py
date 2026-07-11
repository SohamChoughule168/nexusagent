from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.agents import router as agents_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(agents_router)
