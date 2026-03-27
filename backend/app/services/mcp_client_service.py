"""
MCP stdio 클라이언트: 도구 호출만 담당.

주의: MCP_CWD 가 backend 폴더만 가리키면 `mcp_server` 모듈을 찾지 못해 실패한다.
워크스페이스 루트(SAMKWANG AI)를 쓰거나, 잘못된 값이면 자동으로 루트로 보정한다.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from ..config import WORKSPACE_ROOT, Settings, get_settings
from .erp_access import ALLOWED_ERP_TOOLS

logger = logging.getLogger(__name__)


def _resolve_mcp_cwd(settings: Settings) -> Path:
    """mcp_server 패키지가 있는 디렉터리(보통 워크스페이스 루트)를 반환한다."""
    root = Path(WORKSPACE_ROOT).resolve()
    raw = (settings.mcp_cwd or "").strip()
    if not raw:
        return root
    candidate = Path(raw).expanduser().resolve()
    if (candidate / "mcp_server").is_dir():
        return candidate
    logger.warning(
        "MCP_CWD가 유효하지 않습니다(mcp_server 없음): %s → %s 사용",
        candidate,
        root,
    )
    return root


def _stdio_env(cwd: Path) -> dict[str, str]:
    """자식 프로세스에서 `app`·`mcp_server` 모두 import 되도록 PYTHONPATH 설정."""
    env = dict(os.environ)
    extra = f"{cwd / 'backend'}{os.pathsep}{cwd}"
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{old}" if old else extra
    return env


def _tool_result_to_text(result: CallToolResult) -> str:
    if result.isError:
        parts = []
        for block in result.content:
            if isinstance(block, TextContent):
                parts.append(block.text)
        return "도구 오류: " + (" ".join(parts) if parts else "unknown")

    parts: list[str] = []
    for block in result.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
    if result.structuredContent is not None:
        parts.append(json.dumps(result.structuredContent, ensure_ascii=False))
    return "\n".join(parts) if parts else "{}"


def _stdio_params(settings: Settings) -> StdioServerParameters:
    py = settings.mcp_python or sys.executable
    cwd = _resolve_mcp_cwd(settings)
    return StdioServerParameters(
        command=py,
        args=["-m", settings.mcp_module],
        cwd=str(cwd),
        env=_stdio_env(cwd),
    )


@asynccontextmanager
async def erp_mcp_session(settings: Settings | None = None) -> AsyncIterator[ClientSession]:
    """한 번의 MCP stdio 연결로 여러 도구 호출에 재사용한다."""
    settings = settings or get_settings()
    params = _stdio_params(settings)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_erp_tool(name: str, arguments: dict[str, Any], settings: Settings | None = None) -> str:
    """단일 도구 호출(연결 1회). 테스트·단발 호출용."""
    settings = settings or get_settings()
    if name not in ALLOWED_ERP_TOOLS:
        return json.dumps({"error": f"허용되지 않은 도구: {name}"}, ensure_ascii=False)

    async with erp_mcp_session(settings) as session:
        result = await session.call_tool(name, arguments)
        return _tool_result_to_text(result)


async def call_erp_tool_on_session(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
) -> str:
    if name not in ALLOWED_ERP_TOOLS:
        return json.dumps({"error": f"허용되지 않은 도구: {name}"}, ensure_ascii=False)
    result = await session.call_tool(name, arguments)
    return _tool_result_to_text(result)
