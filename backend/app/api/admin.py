"""
관리자 전용 API
"""
from pathlib import Path
from typing import Union

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import require_admin
from ..models.login_account import LoginAccount
from ..models.user import User
from ..services.openai_service import CHAT_MODEL, EMBEDDING_MODEL
from ..services.vector_store import load_vector_store


router = APIRouter()


class AdminOverviewResponse(BaseModel):
    total_users: int
    admin_count_env_hint: str
    indexed_documents: int
    document_files_count: int
    documents_path: str
    vector_db_path: str
    default_chat_model: str
    embedding_model: str
    openai_configured: bool


@router.get("/admin/overview", response_model=AdminOverviewResponse)
async def admin_overview(
    _: Union[User, LoginAccount] = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """시스템 요약(관리자만)."""
    total_users = db.query(func.count(User.user_id)).scalar() or 0

    doc_dir = Path(settings.documents_path)
    file_count = 0
    if doc_dir.exists():
        file_count = sum(1 for p in doc_dir.rglob("*") if p.is_file())

    store = load_vector_store(settings.vector_db_path)
    indexed = store.document_count

    openai_ok = bool(
        settings.openai_api_key and settings.openai_api_key != "changeme-openai-key"
    )

    return AdminOverviewResponse(
        total_users=int(total_users),
        admin_count_env_hint=settings.admin_usernames,
        indexed_documents=indexed,
        document_files_count=file_count,
        documents_path=settings.documents_path,
        vector_db_path=settings.vector_db_path,
        default_chat_model=CHAT_MODEL,
        embedding_model=EMBEDDING_MODEL,
        openai_configured=openai_ok,
    )
