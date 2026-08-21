from unittest.mock import Mock

from src.db.clickhouse_client import execute_create_schemas, execute_drop_schemas


def test_create_schema_migration_executes_each_clickhouse_statement():
    client = Mock()

    execute_create_schemas(client)

    statements = [call.args[0] for call in client.command.call_args_list]
    assert statements[0] == "USE default;"
    assert len(statements) == 16
    assert any("CREATE TABLE IF NOT EXISTS narrative_graph" in statement for statement in statements)
    assert any("CREATE TABLE IF NOT EXISTS element_evidence" in statement for statement in statements)


def test_drop_schema_migration_executes_each_clickhouse_statement():
    client = Mock()

    execute_drop_schemas(client)

    statements = [call.args[0] for call in client.command.call_args_list]
    assert statements[0] == "USE default;"
    assert len(statements) == 16
    assert "DROP TABLE IF EXISTS narrative_graph;" in statements
    assert "DROP TABLE IF EXISTS event_effect;" in statements
