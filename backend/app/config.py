"""
애플리케이션 설정 (.env / 환경 변수).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py → 워크스페이스 루트 (SAMKWANG AI)
WORKSPACE_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """서비스 전역 설정."""

    model_config = SettingsConfigDict(
        env_file=str(WORKSPACE_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # OpenAI
    openai_api_key: str = Field(default="changeme-openai-key")
    default_chat_model: str = Field(default="gpt-4o-mini")

    # 채팅에서 ERP 도구 루프 사용 시 권장 모델(Chat Completions + tools)
    chat_tools_model: str = Field(default="gpt-4o-mini")

    # DB
    database_url: str = Field(default="sqlite:///./samkwang.db")

    # RAG (업로드는 기본 `document` 폴더 — 예전 경로와 통일)
    documents_path: str = Field(default=str(WORKSPACE_ROOT / "document"))
    vector_db_path: str = Field(default=str(WORKSPACE_ROOT / "data" / "vector_db"))
    # 질문 유형별 RAG 우선 검색 하위 경로(document 기준 1단계, 슬래시 없이)
    rag_failure_subdir: str = Field(default="failure encyclopedia")
    rag_knowledge_subdir: str = Field(default="knowledge")
    rag_rules_subdir: str = Field(default="companyrule")

    @field_validator("documents_path", mode="before")
    @classmethod
    def _default_documents_path_if_empty(cls, v: object) -> object:
        if v is None:
            return str(WORKSPACE_ROOT / "document")
        if isinstance(v, str) and not v.strip():
            return str(WORKSPACE_ROOT / "document")
        return v

    @field_validator("vector_db_path", mode="before")
    @classmethod
    def _default_vector_db_path_if_empty(cls, v: object) -> object:
        if v is None:
            return str(WORKSPACE_ROOT / "data" / "vector_db")
        if isinstance(v, str) and not v.strip():
            return str(WORKSPACE_ROOT / "data" / "vector_db")
        return v

    # Auth (.env 에 JWT_SECRET= 만 두면 빈 문자열이 들어가 JWT/세션이 깨질 수 있음)
    jwt_secret: str = Field(default="changeme-jwt-secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60 * 24)

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _jwt_secret_non_empty(cls, v: object) -> object:
        if v is None:
            return "changeme-jwt-secret"
        if isinstance(v, str) and not v.strip():
            return "changeme-jwt-secret"
        return v
    # 쉼표 구분 보조(레거시 users·비상). login 테이블은 `is_admin` 컬럼이 기준.
    admin_usernames: str = Field(default="")

    # ERP HTTP (REST 우선)
    erp_base_url: str = Field(default="")
    erp_auth_mode: str = Field(default="none")  # none | api_key | bearer
    erp_api_key: str = Field(default="")
    erp_api_key_header: str = Field(default="X-API-Key")
    erp_timeout_seconds: float = Field(default=30.0)
    erp_tools_enabled: bool = Field(default=True)

    # MCP stdio 클라이언트 (백엔드 → 별도 프로세스)
    mcp_python: str = Field(default="")
    mcp_module: str = Field(default="mcp_server.mcp_erp_server")
    mcp_cwd: str = Field(default=str(WORKSPACE_ROOT))

    # CORS: "*" 일 때 allow_credentials 는 False 여야 브라우저가 API 호출을 허용함
    # 특정 출처만 허용하려면 예: http://192.168.5.176:8080,http://localhost:5173
    cors_origins: str = Field(default="*")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def resolved_documents_dir(settings: Settings) -> Path:
    """
    DOCUMENTS_PATH가 상대 경로면 워크스페이스 루트(SAMKWANG AI) 기준으로 해석한다.
    uvicorn을 backend/ 등에서 띄워 cwd가 달라도 프로젝트 `document` 폴더를 가리키게 한다.
    """
    raw = (settings.documents_path or "").strip()
    if not raw:
        raw = str(WORKSPACE_ROOT / "document")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (WORKSPACE_ROOT / p).resolve()
    else:
        p = p.resolve()
    return p
