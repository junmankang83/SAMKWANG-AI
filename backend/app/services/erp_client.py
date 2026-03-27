"""
ERP HTTP 어댑터. 타임아웃·에러 매핑·짧은 JSON 정규화.
ERP_BASE_URL 이 비어 있으면 데모용 목 응답을 반환한다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


class ErpClientError(Exception):
    """ERP 호출 실패."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ErpClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return (self._settings.erp_base_url or "").rstrip("/")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        mode = (self._settings.erp_auth_mode or "none").lower()
        if mode == "api_key" and self._settings.erp_api_key:
            h[self._settings.erp_api_key_header] = self._settings.erp_api_key
        elif mode == "bearer" and self._settings.erp_api_key:
            h["Authorization"] = f"Bearer {self._settings.erp_api_key}"
        return h

    def search_items(self, query: str, limit: int = 10) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return {"items": [], "message": "검색어가 비어 있습니다."}

        if not self.base_url:
            return {
                "items": [
                    {"sku": "DEMO-001", "name": "데모 품목 A", "query": q},
                    {"sku": "DEMO-002", "name": "데모 품목 B", "query": q},
                ][: max(1, min(limit, 20))],
                "demo": True,
                "message": "ERP_BASE_URL 미설정: 목 데이터입니다.",
            }

        url = f"{self.base_url}/items/search"
        try:
            with httpx.Client(timeout=self._settings.erp_timeout_seconds) as client:
                r = client.get(url, headers=self._headers(), params={"q": q, "limit": limit})
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            logger.warning("ERP search_items HTTP 오류: %s", e)
            raise ErpClientError(f"ERP 검색 실패: HTTP {e.response.status_code}", e.response.status_code) from e
        except Exception as e:
            logger.exception("ERP search_items 오류")
            raise ErpClientError(f"ERP 검색 중 오류: {e}") from e

        return self._normalize("search_items", data)

    def get_sales_order(self, order_id: str) -> dict[str, Any]:
        oid = (order_id or "").strip()
        if not oid:
            return {"error": "주문 ID가 비어 있습니다."}

        if not self.base_url:
            return {
                "order_id": oid,
                "status": "demo",
                "lines": [{"sku": "DEMO-001", "qty": 1, "price": 1000}],
                "demo": True,
                "message": "ERP_BASE_URL 미설정: 목 데이터입니다.",
            }

        url = f"{self.base_url}/sales-orders/{oid}"
        try:
            with httpx.Client(timeout=self._settings.erp_timeout_seconds) as client:
                r = client.get(url, headers=self._headers())
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPStatusError as e:
            logger.warning("ERP get_sales_order HTTP 오류: %s", e)
            raise ErpClientError(
                f"ERP 주문 조회 실패: HTTP {e.response.status_code}",
                e.response.status_code,
            ) from e
        except Exception as e:
            logger.exception("ERP get_sales_order 오류")
            raise ErpClientError(f"ERP 주문 조회 중 오류: {e}") from e

        return self._normalize("get_sales_order", data)

    def _normalize(self, _tool: str, data: Any) -> dict[str, Any]:
        """LLM 이 쓰기 좋은 얕은 JSON 으로 통일."""
        if isinstance(data, dict):
            return data
        return {"result": data}


def tool_result_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
