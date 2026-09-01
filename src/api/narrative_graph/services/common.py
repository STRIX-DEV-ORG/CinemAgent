"""Shared ClickHouse helpers for narrative graph services."""
from typing import Any


def result_rows(result: Any) -> list[dict[str, Any]]:
    """Convert a ClickHouse result into records keyed by column name."""
    return [dict(zip(result.column_names, row)) for row in result.result_rows]
