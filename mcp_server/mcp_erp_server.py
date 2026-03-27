"""
ERP 연동 MCP 서버 (stdio, FastMCP).

실행: 워크스페이스 루트에서 `python -m mcp_server.mcp_erp_server`
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# 백엔드 패키지(app) 로드
_WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_WORKSPACE / "backend"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.services.erp_access import ERP_TOOL_GET_SALES_ORDER, ERP_TOOL_SEARCH_ITEMS  # noqa: E402
from app.services.erp_client import ErpClient, ErpClientError, tool_result_json  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(name="samkwang-erp")


@mcp.tool(name=ERP_TOOL_SEARCH_ITEMS, description="ERP 품목 마스터에서 키워드로 품목을 검색한다.")
def erp_search_items(query: str, limit: int = 10) -> str:
    client = ErpClient()
    try:
        data = client.search_items(query, limit=min(max(limit, 1), 50))
        return tool_result_json(data)
    except ErpClientError as e:
        logger.warning("search_items: %s", e)
        return tool_result_json({"error": str(e)})


@mcp.tool(name=ERP_TOOL_GET_SALES_ORDER, description="판매 주문 번호로 단건 상세를 조회한다.")
def erp_get_sales_order(order_id: str) -> str:
    client = ErpClient()
    try:
        data = client.get_sales_order(order_id)
        return tool_result_json(data)
    except ErpClientError as e:
        logger.warning("get_sales_order: %s", e)
        return tool_result_json({"error": str(e)})


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
