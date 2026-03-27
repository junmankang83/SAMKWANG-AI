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
    vector_db_path: str = Field(default=str(WORKSPACE_ROOT / "data" / "vector_store.json"))

    @field_validator("documents_path", mode="before")
    @classmethod
    def _default_documents_path_if_empty(cls, v: object) -> object:
        if v is None:
            return str(WORKSPACE_ROOT / "document")
        if isinstance(v, str) and not v.strip():
            return str(WORKSPACE_ROOT / "document")
        return v

    # Auth
    jwt_secret: str = Field(default="changeme-jwt-secret")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60 * 24)
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
