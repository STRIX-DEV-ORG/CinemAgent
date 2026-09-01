"""ADK-compatible HTTP tools for the Narrative Graph API."""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx

from src.config import settings


def _headers(idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {settings.NARRATIVE_API_KEY}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _request(method: str, path: str, payload: dict[str, Any] | None = None,
             idempotency_key: str | None = None) -> str:
    """Call the shared API and return JSON suitable for an LLM tool result."""
    try:
        response = httpx.request(
            method,
            f"{settings.NARRATIVE_API_URL.rstrip('/')}{path}",
            json=payload,
            headers=_headers(idempotency_key),
            timeout=30,
        )
        response.raise_for_status()
        return json.dumps(response.json(), default=str)
    except httpx.HTTPError as error:
        return json.dumps({"status": "error", "message": str(error)})


def query_narrative_subgraph(graph_id: str, query: dict[str, Any] | None = None) -> str:
    """Retrieve a focused graph view before resolving or generating story content."""
    return _request("POST", f"/v1/narrative-graphs/{graph_id}/subgraph:query", query or {})


def submit_narrative_operations(graph_id: str, operations: list[dict[str, Any]],
                                idempotency_key: str | None = None) -> str:
    """Persist validation-approved, typed graph operations as one ordered batch."""
    return _request(
        "POST",
        f"/v1/narrative-graphs/{graph_id}/operation-batches",
        {"operations": operations},
        idempotency_key or str(uuid4()),
    )


def get_operation_batch(graph_id: str, batch_id: str) -> str:
    """Poll a write batch until it has reached the applied or failed state."""
    return _request("GET", f"/v1/narrative-graphs/{graph_id}/operation-batches/{batch_id}")
