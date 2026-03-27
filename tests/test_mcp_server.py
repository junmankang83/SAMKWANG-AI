from mcp_server.database.db_manager import DatabaseManager


def test_db_manager_has_default_url() -> None:
    manager = DatabaseManager(database_url="postgresql://user:password@localhost:5432/testdb")
    assert "testdb" in manager.database_url

