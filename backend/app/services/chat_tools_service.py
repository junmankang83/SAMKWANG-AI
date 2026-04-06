"""
RAG 컨텍스트 + OpenAI tools + MCP(stdio) 도구 루프.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import List, Tuple

from openai import OpenAI

from ..config import Settings
from .erp_tools_spec import openai_erp_tool_definitions
from .mcp_client_service import call_erp_tool_on_session, erp_mcp_session
from .openai_service import CHAT_SYSTEM_PROMPT
from .rag_service import retrieve_matches_for_chat

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


def _build_openai_client(settings: Settings) -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


async def answer_question_with_erp_tools(
    query: str,
    conversation_id: str | None,
    model: str | None,
    settings: Settings,
) -> Tuple[str, List[str]]:
    """
    RAG 유사도 검색 후, ERP MCP 도구를 호출할 수 있는 채팅 완성 루프.
    """
    logger.debug("요청 모델=%s (도구 루프 실제 사용=%s)", model, settings.chat_tools_model)
    matches, scope_label = retrieve_matches_for_chat(query, settings, k=5)
    if matches:
        context = "\n---\n".join(doc for doc, _meta in matches)
    else:
        context = "No context available."
    references = [meta.get("filename", "unknown") for _doc, meta in matches]

    # 프론트에서 선택한 모델로 Chat Completions(+tools). 비어 있으면 CHAT_TOOLS_MODEL
    requested = (model or "").strip()
    tools_model = requested if requested else settings.chat_tools_model
    logger.info("OpenAI 채팅(도구) 호출 모델: %s", tools_model)
    client = _build_openai_client(settings)

    user_blob = (
        f"Conversation: {conversation_id or 'new'}\n\n"
        f"검색 우선 영역: {scope_label}\n\n"
        f"문서 컨텍스트:\n{context}\n\n사용자 질문:\n{query}"
    )

    messages: list = [
        {
            "role": "system",
            "content": CHAT_SYSTEM_PROMPT
            + "\n\nERP 데이터가 필요하면 제공된 도구를 호출하세요. 도구 결과를 바탕으로 한국어로 답하세요.",
        },
        {"role": "user", "content": user_blob},
    ]
    tools = openai_erp_tool_definitions()

    # 도구가 필요할 때만 MCP stdio 프로세스를 띄운다(일반 대화는 MCP 없이 동작).
    async with AsyncExitStack() as stack:
        mcp_session = None
        for round_i in range(MAX_TOOL_ROUNDS):
            try:
                resp = await asyncio.to_thread(
                    lambda: client.chat.completions.create(
                        model=tools_model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.7,
                        max_tokens=2500,
                    )
                )
            except Exception as exc:
                logger.exception("OpenAI tools 채팅 호출 실패")
                msg = str(exc)
                if "invalid_api_key" in msg or "Incorrect API key" in msg:
                    return (
                        "OpenAI API 키가 올바르지 않습니다. "
                        "프로젝트 루트 `.env`에 `OPENAI_API_KEY`를 실제 키로 설정해 주세요.",
                        references,
                    )
                if "insufficient_quota" in msg:
                    return (
                        "OpenAI API 사용 한도(쿼터)를 초과했습니다. "
                        "요금제/쿼터를 확인해 주세요.",
                        references,
                    )
                return (
                    "채팅(도구 연동) 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                    references,
                )

            msg = resp.choices[0].message
            if not msg.tool_calls:
                return (msg.content or "").strip() or "(빈 응답)", references

            if mcp_session is None:
                try:
                    mcp_session = await stack.enter_async_context(erp_mcp_session(settings))
                except Exception:
                    logger.exception("MCP 세션 시작 실패")
                    return (
                        "ERP/MCP 서버를 시작할 수 없습니다. "
                        "프로젝트 루트에 `mcp_server` 폴더가 있는지, "
                        "백엔드 가상환경에 `mcp` 패키지가 설치되어 있는지 확인해 주세요. "
                        "(또는 MCP_PYTHON 에 백엔드 .venv/bin/python 경로를 지정하세요.)",
                        references,
                    )

            assistant_msg: dict = {"role": "assistant", "content": msg.content}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in msg.tool_calls
            ]
            messages.append(assistant_msg)

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info(
                    "ERP MCP 도구 감사 로그: round=%s tool=%s args=%s",
                    round_i,
                    name,
                    args,
                )
                try:
                    tool_text = await call_erp_tool_on_session(mcp_session, name, args)
                except Exception as exc:
                    logger.exception("MCP 도구 실행 실패")
                    tool_text = json.dumps(
                        {"error": f"도구 실행 실패: {exc}"},
                        ensure_ascii=False,
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_text,
                    }
                )

    return (
        "도구 호출이 너무 많이 반복되어 중단되었습니다. 질문을 더 구체적으로 입력해 주세요.",
        references,
    )
