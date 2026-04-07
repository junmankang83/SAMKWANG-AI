"""
FastAPI 애플리케이션 진입점.
"""

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router as api_router
from .config import get_settings
from .database import Base, engine, ensure_login_admin_column_and_seed
from .services.rag_service import sync_documents_folder
from .models import login_account as _login_model  # noqa: F401
from .models import user as _user_model  # noqa: F401  # 테이블 메타데이터 등록용 임포트

logger = logging.getLogger(__name__)


def _cors_allow_credentials(origins: list[str]) -> bool:
    """브라우저 스펙: allow_origins=['*'] 일 때 allow_credentials 는 False 여야 함."""
    return origins != ["*"]


def _parse_cors_origins(raw: str) -> list[str]:
    s = (raw or "*").strip()
    if s == "*":
        return ["*"]
    parts = [x.strip() for x in s.split(",") if x.strip()]
    return parts if parts else ["*"]


_settings = get_settings()
_cors_origins = _parse_cors_origins(_settings.cors_origins)
_cors_credentials = _cors_allow_credentials(_cors_origins)


async def _rag_sync_background() -> None:
    """기동 직후 API 가용성을 막지 않도록 RAG 전체 동기화는 스레드에서 실행."""
    try:
        stats = await asyncio.to_thread(sync_documents_folder, _settings)
        logger.info(
            "RAG 문서 동기화 완료: 청크=%s 파일=%s skipped=%s",
            stats["indexed"],
            stats.get("indexed_files", 0),
            stats["skipped"],
        )
    except Exception:
        logger.exception("RAG 문서 동기화 실패(서버 기동은 계속)")


app = FastAPI(title="SAMKWANG AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
async def ensure_db_tables() -> None:
    """
    인증용 `users`·`login` 테이블이 없을 때 500이 나는 문제를 방지.
    DATABASE_URL이 PostgreSQL이면 해당 DB에, SQLite면 해당 파일에 생성된다.
    """
    Base.metadata.create_all(bind=engine)
    ensure_login_admin_column_and_seed(engine)
    asyncio.create_task(_rag_sync_background())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """프론트가 잘못된 JSON을 보낼 때 422 대신 메시지를 알기 쉽게."""
    logger.warning("요청 검증 실패: %s %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "detail": "요청 형식이 올바르지 않습니다. message 필드가 있는지 확인해 주세요.",
            "errors": exc.errors(),
        },
    )


@app.get("/")
async def root():
    return {
        "service": "SAMKWANG AI API",
        "health": "/health",
        "docs": "/docs",
        "api_chat": "/api/chat",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
