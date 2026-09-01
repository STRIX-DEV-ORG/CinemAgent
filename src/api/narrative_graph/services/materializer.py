"""Apply accepted journal operations to canonical ClickHouse graph tables."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ..models import OperationType
from .common import result_rows


class OperationMaterializer:
    _CREATE_TABLES = {
        OperationType.CREATE_ENTITY: "entity",
        OperationType.CREATE_TIME: "time",
        OperationType.CREATE_CONTEXT: "context",
        OperationType.CREATE_EVENT: "event",
        OperationType.CREATE_EVENT_PARTICIPANT: "event_participant",
        OperationType.CREATE_KNOWLEDGE_ELEMENT: "knowledge_element",
        OperationType.CREATE_ATTRIBUTE: "attribute",
        OperationType.CREATE_STATEMENT: "statement",
        OperationType.CREATE_EVENT_EFFECT: "event_effect",
        OperationType.CREATE_EVENT_RELATION: "event_relation",
        OperationType.CREATE_SOURCE_SEGMENT: "source_segment",
        OperationType.CREATE_EVIDENCE: "evidence",
        OperationType.LINK_EVIDENCE: "element_evidence",
    }

    def __init__(self, client: Any) -> None:
        self.client = client

    @staticmethod
    def _literal(value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return "'" + str(value).replace("'", "\\'") + "'"

    def _apply_operation(self, operation: dict[str, Any]) -> None:
        operation_type = OperationType(operation["operation_type"])
        payload = json.loads(operation["payload"]) if isinstance(operation["payload"], str) else operation["payload"]
        if operation_type in self._CREATE_TABLES:
            table = self._CREATE_TABLES[operation_type]
            if table in {"entity", "time", "context", "event", "knowledge_element", "source_segment"}:
                payload.setdefault("graph_id", str(operation["graph_id"]))
            columns = list(payload)
            self.client.insert(table, [[payload[column] for column in columns]], column_names=columns)
            return
        if operation_type in {OperationType.UPDATE_ENTITY, OperationType.UPDATE_EVENT}:
            table = "entity" if operation_type == OperationType.UPDATE_ENTITY else "event"
            changes = payload["changes"]
            allowed = {"name", "type", "status", "description", "confidence", "aliases", "metadata", "time_id"}
            if not set(changes).issubset(allowed):
                raise ValueError("update includes unsupported fields")
            assignments = ", ".join(f"{key} = {self._literal(value)}" for key, value in changes.items())
            self.client.command(f"ALTER TABLE {table} UPDATE {assignments} WHERE id = {self._literal(payload['id'])}")
            return
        if operation_type == OperationType.INVALIDATE_STATEMENT:
            self.client.command("ALTER TABLE knowledge_element UPDATE status = 'invalidated' " f"WHERE id = {self._literal(payload['id'])}")
            return
        if operation_type == OperationType.MERGE_ENTITY:
            self.client.command(
                "ALTER TABLE entity UPDATE status = 'merged', metadata = "
                f"JSONSet(metadata, 'merged_into', {self._literal(payload['target_id'])}) "
                f"WHERE id = {self._literal(payload['source_id'])}"
            )

    def materialize_batch(self, graph_id: UUID, batch_id: UUID) -> None:
        self.client.command(f"ALTER TABLE operation_batch UPDATE status = 'applying', updated_at = now64(3) WHERE id = '{batch_id}'")
        result = self.client.query(
            "SELECT id, graph_id, operation_type, payload FROM graph_operation "
            "WHERE batch_id = {batch_id:UUID} ORDER BY sequence", parameters={"batch_id": batch_id},
        )
        try:
            for operation in result_rows(result):
                self._apply_operation(operation)
                self.client.command(f"ALTER TABLE graph_operation UPDATE status = 'applied', applied_at = now64(3) WHERE id = '{operation['id']}'")
            self.client.command(f"ALTER TABLE operation_batch UPDATE status = 'applied', updated_at = now64(3) WHERE id = '{batch_id}'")
        except Exception as error:
            self.client.command(
                "ALTER TABLE operation_batch UPDATE status = 'failed', error = "
                f"{self._literal(str(error))}, updated_at = now64(3) WHERE id = '{batch_id}'"
            )
