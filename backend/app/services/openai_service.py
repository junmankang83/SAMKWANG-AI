"""
OpenAI API 연동 래퍼.
실제 환경에서는 openai 패키지를 사용해 GPT 및 임베딩을 호출한다.
GPT-5.x 계열은 Responses API, 그 외는 Chat Completions API를 사용한다.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Iterable

from openai import OpenAI

from ..config import get_settings

# Settings에서 API 키 가져오기
settings = get_settings()

logger = logging.getLogger(__name__)

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=settings.openai_api_key)

# RAG 채팅 시스템 프롬프트 (Chat Completions / Responses instructions 공통)
CHAT_SYSTEM_PROMPT = """당신은 SAMKWANG AI 어시스턴트입니다. 사용자의 질문에 친절하고 상세하게 답변하는 전문 AI입니다.

답변 가이드라인:
1. **자세하고 포괄적으로**: 질문에 대해 다양한 관점과 맥락을 포함하여 깊이 있게 설명하세요.
2. **구조화된 답변**: 복잡한 내용은 번호나 불릿 포인트로 정리하여 이해하기 쉽게 제시하세요.
3. **예시 제공**: 가능한 경우 구체적인 예시나 사례를 들어 설명하세요.
4. **추가 정보**: 질문과 관련된 유용한 배경 지식이나 팁을 함께 제공하세요.
5. **명확한 언어**: 전문 용어는 쉽게 풀어서 설명하고, 한국어로 자연스럽게 답변하세요.
6. **맥락 고려**: 질문의 의도를 파악하여 가장 유용한 정보를 우선적으로 제공하세요.
7. **객관성 유지**: 여러 관점이나 해석이 있을 경우 균형있게 제시하세요.

제공된 문서 컨텍스트가 있다면 이를 우선적으로 활용하되, 일반적인 지식도 함께 제공하여 완전한 답변을 만드세요."""

# 사용할 모델 버전 설정 (.env 의 DEFAULT_CHAT_MODEL 로 덮어쓰기 가능)
CHAT_MODEL = settings.default_chat_model
EMBEDDING_MODEL = "text-embedding-3-small"  # 최신 임베딩 모델


def _uses_responses_api(model: str) -> bool:
    """GPT-5 계열은 Responses API 권장."""
    m = (model or "").strip().lower()
    return m.startswith("gpt-5")


def generate_chat_completion(prompt: str, model: str = CHAT_MODEL) -> str:
    """
    OpenAI API를 사용하여 채팅 완성을 생성합니다.

    Args:
        prompt: 사용자 프롬프트(컨텍스트 + 질문 등)
        model: 사용할 OpenAI 모델 (기본값: 설정의 default_chat_model)

    Returns:
        생성된 응답 텍스트
    """
    try:
        print(f"[OpenAI Service] 사용할 모델: {model}")
        if _uses_responses_api(model):
            # Responses API: instructions + input. reasoning effort none 시 temperature/top_p 사용 가능.
            response = client.responses.create(
                model=model,
                instructions=CHAT_SYSTEM_PROMPT,
                input=prompt,
                reasoning={"effort": "none"},
                temperature=0.8,
                max_output_tokens=2000,
                top_p=0.95,
                text={"verbosity": "medium"},
            )
            text = (response.output_text or "").strip()
            return text if text else "응답을 생성하지 못했습니다."

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=2000,
            top_p=0.95,
            frequency_penalty=0.3,
            presence_penalty=0.3,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"OpenAI API 호출 중 오류 발생: {str(e)}"


def embed_query_text(text: str, model: str = EMBEDDING_MODEL) -> list[float] | None:
    """
    단일 질의/문장 임베딩. 실패 시 None (폴백 검색용).
    """
    t = (text or "").strip()
    if not t:
        return None
    try:
        response = client.embeddings.create(model=model, input=[t])
        return list(response.data[0].embedding)
    except Exception as exc:
        logger.warning("쿼리 임베딩 실패: %s", exc)
        return None


def embed_documents(documents: Iterable[str], model: str = EMBEDDING_MODEL) -> list[list[float]]:
    """
    문서 임베딩 생성.

    Args:
        documents: 임베딩할 문서 리스트
        model: 사용할 임베딩 모델 (기본값: text-embedding-3-small)

    Returns:
        임베딩 벡터 리스트
    """
    documents_list: list[str] = []
    try:
        documents_list = list(documents)
        if not documents_list:
            return []

        response = client.embeddings.create(
            model=model,
            input=documents_list,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"임베딩 생성 중 오류 발생: {str(e)}")
        # 오류 발생 시 더미 데이터 반환
        return [[0.0 for _ in range(1536)] for _ in documents_list]


def extract_text_from_image(image_path: Path, model: str = "gpt-4o-mini") -> str:
    """
    OpenAI 비전 모델을 사용해 이미지에서 텍스트를 추출한다.
    """

    try:
        image_bytes = image_path.read_bytes()
        mime = "image/png"
        suffix = image_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif suffix == ".webp":
            mime = "image/webp"

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "이 문서 이미지에서 읽을 수 있는 텍스트를 최대한 정확히 추출해서 평문으로만 반환해줘.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=2000,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"이미지 OCR 중 오류 발생: {exc}")
        return ""
