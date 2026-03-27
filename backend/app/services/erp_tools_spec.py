"""
OpenAI Chat Completions `tools` 스키마 (이름은 MCP 서버 도구와 동일).
"""

from __future__ import annotations

from typing import Any

from .erp_access import ERP_TOOL_GET_SALES_ORDER, ERP_TOOL_SEARCH_ITEMS


def openai_erp_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": ERP_TOOL_SEARCH_ITEMS,
                "description": "ERP 품목 마스터에서 키워드로 품목을 검색한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "검색 키워드"},
                        "limit": {
                            "type": "integer",
                            "description": "최대 결과 수(1~50)",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": ERP_TOOL_GET_SALES_ORDER,
                "description": "판매 주문 번호로 단건 상세를 조회한다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "주문 ID 또는 주문 번호",
                        },
                    },
                    "required": ["order_id"],
                },
            },
        },
    ]
