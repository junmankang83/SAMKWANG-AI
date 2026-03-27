import os
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DEFAULT_URL = "postgresql://user:password@localhost:5432/chatbot"


class DatabaseManager:
    """
    SQLAlchemy 엔진을 통한 단순 DB 헬퍼.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL", DEFAULT_URL)
        self.engine: Engine = create_engine(self.database_url, echo=False, future=True)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        with self.engine.connect() as conn:
            yield conn

    def execute(self, sql: str) -> None:
        with self.connect() as conn:
            conn.execute(text(sql))
            conn.commit()

    def fetchall(self, sql: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            result = conn.execute(text(sql))
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def list_tables(self) -> list[str]:
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY table_name;
        """
        try:
            rows = self.fetchall(query)
        except Exception:  # noqa: BLE001
            return []
        return [row["table_name"] for row in rows]

