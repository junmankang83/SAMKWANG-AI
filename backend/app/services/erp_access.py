"""
ERP 연동 접근 모델(고정 가정).

운영 전 실제 ERP 사양에 맞게 엔드포인트·스키마만 바꾸면 되도록,
여기서는 **HTTP REST API** 를 1차 연동 방식으로 둔다.

- **DB 직접 조회**: 계획상 읽기 전용·별도 ETL이 안전하나, 본 구현에서는
  QueryTool 스타일의 임의 SQL 은 노출하지 않는다.
- **인증**: API Key(헤더) 또는 Bearer 토큰(환경변수로 비밀만 주입).
- **조회 범위**: 품목 검색·판매주문 단건 조회만 도구로 노출(최소 데모).
"""

from enum import Enum


class ErpAuthMode(str, Enum):
    """ERP HTTP 인증 방식."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"


# OpenAI / MCP 에 노출할 도구 이름 (MCP 서버·백엔드 도구 스펙과 동일해야 함)
ERP_TOOL_SEARCH_ITEMS = "erp_search_items"
ERP_TOOL_GET_SALES_ORDER = "erp_get_sales_order"

# 허용된 도구 집합(백엔드에서 추가 검증)
ALLOWED_ERP_TOOLS = frozenset({ERP_TOOL_SEARCH_ITEMS, ERP_TOOL_GET_SALES_ORDER})
