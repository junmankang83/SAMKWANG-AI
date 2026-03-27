"""
MCP 서버 진입점.

- 기본: `mcp_server.mcp_erp_server` 의 FastMCP(stdio) 실행.
- `MCP_SIMULATION=1` 이면 예전 DB 툴 시뮬레이션 루프(시간 점유).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def _run_simulation() -> None:
    from .database.db_manager import DatabaseManager
    from .tools.database_tool import DatabaseTool
    from .tools.query_tool import QueryTool

    db_manager = DatabaseManager()
    db_tool = DatabaseTool(db_manager)
    query_tool = QueryTool(db_manager)

    logger.info("Starting MCP tool simulation (MCP_SIMULATION=1)...")
    logger.info("Existing tables: %s", db_manager.list_tables())
    logger.info("Database tool ready: %s", db_tool.describe())
    logger.info("Query tool ready: %s", query_tool.describe())

    while True:
        await asyncio.sleep(3600)


def main() -> Any:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if os.environ.get("MCP_SIMULATION", "").strip() == "1":
        try:
            asyncio.run(_run_simulation())
        except KeyboardInterrupt:
            logger.info("MCP simulation stopped.")
        return

    from .mcp_erp_server import main as erp_main

    erp_main()


if __name__ == "__main__":
    main()
