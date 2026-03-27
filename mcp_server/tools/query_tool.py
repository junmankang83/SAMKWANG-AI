from typing import Any

from ..database.db_manager import DatabaseManager


class QueryTool:
    """
    임의 SQL을 실행해 결과를 반환하는 MCP 도구.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def describe(self) -> str:
        return "Executes read-only SQL queries against PostgreSQL."

    def run(self, sql: str) -> list[dict[str, Any]]:
        return self.db_manager.fetchall(sql)

