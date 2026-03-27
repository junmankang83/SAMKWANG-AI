from typing import Any

from ..database.db_manager import DatabaseManager


class DatabaseTool:
    """
    데이터베이스 스키마를 생성/삭제하는 MCP 도구.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db_manager = db_manager

    def describe(self) -> str:
        return "Creates tables defined in the MCP schema catalogue."

    def create_sample_schema(self) -> dict[str, Any]:
        """
        예시 테이블을 생성한다.
        """

        sql = """
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.db_manager.execute(sql)
        return {"status": "created", "table": "documents"}

