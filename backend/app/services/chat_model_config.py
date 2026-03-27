"""
프론트·API에서 선택 가능한 OpenAI 채팅 모델 ID 화이트리스트.
목록에 없는 값은 기본 모델로 대체한다(임의 모델명·주입 방지).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# OpenAI 대시보드에서 실제 사용 가능한 ID와 맞출 것
ALLOWED_CHAT_MODELS: frozenset[str] = frozenset(
    {
        "gpt-3.5-turbo",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4",
        "gpt-5",
        "gpt-5.4",
    }
)

# Chat Completions + tools 경로에서 안정적으로 쓰는 모델 집합
TOOLS_CHAT_MODELS: frozenset[str] = frozenset(
    {
        "gpt-3.5-turbo",
        "gpt-4-turbo",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-5",
        "gpt-5.4",
    }
)

# 프론트에서 짧은 라벨/별칭이 들어와도 실제 OpenAI 모델 ID로 정규화
MODEL_ALIASES: dict[str, str] = {
    "gpt-3.5": "gpt-3.5-turbo",
    "gpt-4": "gpt-4-turbo",
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o": "gpt-4o",
    "gpt-5": "gpt-5",
    "gpt-5.4": "gpt-5.4",
}


def normalize_chat_model(requested: str | None, fallback: str) -> str:
    if not requested:
        return fallback
    m = requested.strip().lower()
    m = MODEL_ALIASES.get(m, m)
    if m in ALLOWED_CHAT_MODELS:
        return m
    logger.warning("허용 목록에 없는 모델 요청 무시: %s → %s", m, fallback)
    return fallback


def normalize_tools_chat_model(requested: str | None, fallback: str) -> str:
    """
    ERP 도구 루프(Chat Completions + tools)에 안전한 모델만 허용.
    """
    normalized = normalize_chat_model(requested, fallback)
    if normalized in TOOLS_CHAT_MODELS:
        return normalized
    logger.warning(
        "도구 루프 미지원 모델 요청 무시: %s → %s",
        normalized,
        fallback,
    )
    return fallback
