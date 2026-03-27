from fastapi import APIRouter

from .admin import router as admin_router
from .auth import router as auth_router
from .chat import router as chat_router
from .documents import router as documents_router

router = APIRouter()
router.include_router(chat_router, tags=["chat"])
router.include_router(documents_router, tags=["documents"])
router.include_router(auth_router, tags=["auth"])
router.include_router(admin_router, tags=["admin"])

