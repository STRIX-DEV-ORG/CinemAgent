"""Operation batch validation and journal persistence."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from ..models import OperationBatchCreate, OperationBatchResponse, OperationType
from .common import result_rows
from .graphs import GraphService


class OperationBatchService:
    _CREATE_OPERATIONS = {
        OperationType.CREATE_ENTITY,
        OperationType.CREATE_TIME,
        OperationType.CREATE_CONTEXT,
        OperationType.CREATE_EVENT,
        OperationType.CREATE_EVENT_PARTICIPANT,
        OperationType.CREATE_KNOWLEDGE_ELEMENT,
        OperationType.CREATE_ATTRIBUTE,
        OperationType.CREATE_STATEMENT,
        OperationType.CREATE_RELATION,
        OperationType.CREATE_EVENT_EFFECT,
        OperationType.CREATE_EVENT_RELATION,
        OperationType.CREATE_SOURCE_SEGMENT,
        OperationType.CREATE_EVIDENCE,
        OperationType.LINK_EVIDENCE,
    }

    def __init__(self, client: Any, graphs: GraphService) -> None:
        self.client = client
        self.graphs = graphs
        self.intelligence: Any | None = None

    def _validate_batch(self, graph_id: UUID, batch: OperationBatchCreate) -> None:
        self.graphs.get_graph(graph_id)
        created_ids = {str(item.payload["id"]) for item in batch.operations if item.payload.get("id")}
        for operation in batch.operations:
            payload = operation.payload
            if operation.operation_type in self._CREATE_OPERATIONS and operation.operation_type != OperationType.LINK_EVIDENCE:
                if "id" not in payload:
                    raise HTTPException(status_code=422, detail=f"{operation.operation_type.value} requires payload.id")
            if operation.operation_type in {OperationType.UPDATE_ENTITY, OperationType.UPDATE_EVENT}:
                if not payload.get("id") or not payload.get("changes"):
                    raise HTTPException(status_code=422, detail=f"{operation.operation_type.value} requires id and changes")
            if operation.operation_type == OperationType.UPDATE_NODE:
                if not payload.get("id") or not payload.get("changes") or payload.get("node_type") not in {"entity", "event", "context", "knowledge_element"}:
                    raise HTTPException(status_code=422, detail="update_node requires an id, changes, and supported node_type")
            if operation.operation_type == OperationType.UPDATE_RELATION:
                if not payload.get("id") or not payload.get("changes"):
                    raise HTTPException(status_code=422, detail="update_relation requires an id and changes")
            if operation.operation_type == OperationType.DELETE_RELATION and not payload.get("id"):
                raise HTTPException(status_code=422, detail="delete_relation requires an id")
            if operation.operation_type == OperationType.INVALIDATE_STATEMENT and not payload.get("id"):
                raise HTTPException(status_code=422, detail="invalidate_statement requires the statement id")
            if operation.operation_type == OperationType.DELETE_NODE:
                if not payload.get("id") or payload.get("node_type") not in {"entity", "event", "context", "knowledge_element"}:
                    raise HTTPException(status_code=422, detail="delete_node requires an id and supported node_type")
            if operation.operation_type == OperationType.LINK_NODE_TO_CHAPTER:
                if not payload.get("chapter_id") or not payload.get("node_id") or payload.get("node_type") not in {"entity", "event", "context", "knowledge_element", "relation"}:
                    raise HTTPException(status_code=422, detail="link_node_to_chapter requires chapter_id, node_id, and supported node_type")
            if operation.operation_type == OperationType.MERGE_ENTITY and not (payload.get("source_id") and payload.get("target_id")):
                raise HTTPException(status_code=422, detail="merge_entity requires source_id and target_id")
            if payload.get("graph_id") and str(payload["graph_id"]) != str(graph_id):
                raise HTTPException(status_code=422, detail="payload graph_id must match the request path")

            for key in ("entity_id", "event_id", "time_id", "context_id", "source_segment_id"):
                if payload.get(key) and str(payload[key]) in created_ids:
                    continue

    def submit_batch(self, graph_id: UUID, idempotency_key: str, batch: OperationBatchCreate) -> OperationBatchResponse:
        self._validate_batch(graph_id, batch)
        result = self.client.query(
            "SELECT id, status, operation_count, error FROM operation_batch "
            "WHERE graph_id = {graph_id:UUID} AND idempotency_key = {idempotency_key:String} LIMIT 1",
            parameters={"graph_id": graph_id, "idempotency_key": idempotency_key},
        )
        rows = result_rows(result)
        if rows:
            return OperationBatchResponse(graph_id=graph_id, **rows[0])

        batch_id = uuid4()
        self.client.insert(
            "operation_batch",
            [[batch_id, graph_id, idempotency_key, "accepted", len(batch.operations), None]],
            column_names=["id", "graph_id", "idempotency_key", "status", "operation_count", "error"],
        )
        operation_rows = [
            [item.id, batch_id, graph_id, sequence, item.operation_type.value,
             json.dumps(item.payload), json.dumps(item.provenance), item.origin, "accepted", None]
            for sequence, item in enumerate(batch.operations)
        ]
        self.client.insert(
            "graph_operation", operation_rows,
            column_names=["id", "batch_id", "graph_id", "sequence", "operation_type", "payload", "provenance", "origin", "status", "error"],
        )
        # The operation journal remains API-compatible, while every accepted
        # operation is also emitted into the immutable ClickHouse event stream.
        if self.intelligence:
            for sequence, item in enumerate(batch.operations, start=1):
                metadata = item.payload.get("metadata")
                chapter_id = item.payload.get("chapter_id") or (metadata.get("chapter_id") if isinstance(metadata, dict) else None)
                self.intelligence.append_event(
                    graph_id,
                    item.operation_type.value,
                    actor_type=item.origin,
                    chapter_id=UUID(str(chapter_id)) if chapter_id else None,
                    batch_id=batch_id,
                    operation_id=item.id,
                    version=sequence,
                    payload=item.payload,
                    provenance=item.provenance,
                )
        return OperationBatchResponse(id=batch_id, graph_id=graph_id, status="accepted", operation_count=len(batch.operations))

    def get_batch(self, graph_id: UUID, batch_id: UUID) -> OperationBatchResponse:
        result = self.client.query(
            "SELECT id, status, operation_count, error FROM operation_batch "
            "WHERE id = {id:UUID} AND graph_id = {graph_id:UUID} ORDER BY updated_at DESC LIMIT 1",
            parameters={"id": batch_id, "graph_id": graph_id},
        )
        rows = result_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="operation batch not found")
        return OperationBatchResponse(graph_id=graph_id, **rows[0])
