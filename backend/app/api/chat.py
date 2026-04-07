import logging

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..models.schemas import ChatRequest, ChatResponse
from ..services.chat_model_config import normalize_chat_model, normalize_tools_chat_model
from ..services.chat_tools_service import answer_question_with_erp_tools
from ..services.openai_service import CHAT_MODEL
from ..services.rag_service import answer_question

logger = logging.getLogger(__name__)

router = APIRouter()

def _append_rag_sources(answer: str, sources: list[str]) -> str:
    if not sources:
        return answer
    uniq: list[str] = []
    seen: set[str] = set()
    for s in sources:
        name = str(s or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        uniq.append(name)
    if not uniq:
        return answer
    return (
        answer.rstrip()
        + "\n\n[문서 기반 참고]\n- "
        + "\n- ".join(uniq)
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """
    사용자 질문을 받아 RAG 파이프라인과 OpenAI 응답을 반환한다.
    ERP 도구가 켜져 있으면 MCP(stdio) 도구 루프 경로를 사용한다.
    """

    model = normalize_chat_model(payload.model, CHAT_MODEL)
    tools_model = normalize_tools_chat_model(payload.model, settings.chat_tools_model)

    try:
        rag_folder = payload.rag_folder
        if settings.erp_tools_enabled:
            answer, sources = await answer_question_with_erp_tools(
                query=payload.message,
                conversation_id=payload.conversation_id,
                model=tools_model,
                settings=settings,
                rag_folder=rag_folder,
            )
            # 도구 루프가 실패하면 일반 RAG 채팅 경로로 한 번 더 시도
            if answer.startswith("채팅(도구 연동) 처리 중 오류"):
                answer, sources = answer_question(
                    query=payload.message,
                    conversation_id=payload.conversation_id,
                    model=model,
                    settings=settings,
                    rag_folder=rag_folder,
                )
        else:
            answer, sources = answer_question(
                query=payload.message,
                conversation_id=payload.conversation_id,
                model=model,
                settings=settings,
                rag_folder=rag_folder,
            )
    except Exception:
        logger.exception("채팅 처리 중 예외 (500 대신 응답 본문으로 안내)")
        return ChatResponse(
            answer=(
                "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. "
                "문제가 계속되면 관리자에게 문의하세요."
            ),
            references=[],
        )

    return ChatResponse(
        answer=_append_rag_sources(answer, sources),
        references=sources,
    )

