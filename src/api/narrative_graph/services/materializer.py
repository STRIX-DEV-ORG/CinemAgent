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
        OperationType.CREATE_RELATION: "graph_relation",
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
        if isinstance(value, list):
            return "[" + ", ".join(OperationMaterializer._literal(item) for item in value) + "]"
        if isinstance(value, dict):
            value = json.dumps(value)
        return "'" + str(value).replace("'", "\\'") + "'"

    def _apply_operation(self, operation: dict[str, Any]) -> None:
        operation_type = OperationType(operation["operation_type"])
        payload = json.loads(operation["payload"]) if isinstance(operation["payload"], str) else operation["payload"]
        if operation_type in self._CREATE_TABLES:
            table = self._CREATE_TABLES[operation_type]
            if table in {"entity", "time", "context", "event", "knowledge_element", "source_segment", "graph_relation"}:
                payload.setdefault("graph_id", str(operation["graph_id"]))
            columns = list(payload)
            self.client.insert(table, [[payload[column] for column in columns]], column_names=columns)
            return
        if operation_type == OperationType.LINK_NODE_TO_CHAPTER:
            self.client.insert(
                "chapter_node",
                [[operation["graph_id"], payload["chapter_id"], payload["node_id"], payload["node_type"]]],
                column_names=["graph_id", "chapter_id", "node_id", "node_type"],
            )
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
        if operation_type == OperationType.UPDATE_NODE:
            node_type = payload["node_type"]
            table = node_type
            allowed_by_type = {
                "entity": {"name", "type", "status", "description", "content", "confidence", "aliases", "metadata"},
                "event": {"name", "type", "status", "description", "content", "confidence", "metadata", "time_id"},
                "context": {"name", "type", "description", "content", "holder_entity_id", "confidence", "metadata"},
                "knowledge_element": {"name", "time_id", "context_id", "element_type", "description", "content", "origin", "status", "confidence", "metadata"},
            }
            changes = payload["changes"]
            if not set(changes).issubset(allowed_by_type[node_type]):
                raise ValueError("update includes unsupported fields")
            key_column = "element_type" if node_type == "knowledge_element" else "type"
            if key_column in changes:
                existing = result_rows(self.client.query(
                    f"SELECT * FROM {table} WHERE id = {self._literal(payload['id'])} LIMIT 1"
                ))
                if not existing:
                    raise ValueError("graph element not found")
                replacement = existing[0]
                replacement.update(changes)
                self.client.command(
                    f"ALTER TABLE {table} DELETE WHERE id = {self._literal(payload['id'])} SETTINGS mutations_sync = 1"
                )
                columns = list(replacement)
                self.client.insert(table, [[replacement[column] for column in columns]], column_names=columns)
                return
            assignments = ", ".join(f"{key} = {self._literal(value)}" for key, value in changes.items())
            self.client.command(f"ALTER TABLE {table} UPDATE {assignments} WHERE id = {self._literal(payload['id'])}")
            return
        if operation_type == OperationType.UPDATE_RELATION:
            changes = payload["changes"]
            allowed = {"source_node_id", "target_node_id", "label", "description", "status", "confidence", "metadata"}
            if not set(changes).issubset(allowed):
                raise ValueError("relation update includes unsupported fields")
            existing = result_rows(self.client.query(
                f"SELECT relation_type FROM graph_relation WHERE id = {self._literal(payload['id'])} LIMIT 1"
            ))
            if not existing:
                raise ValueError("graph relation not found")
            assignments = ", ".join(f"{key} = {self._literal(value)}" for key, value in changes.items())
            self.client.command(f"ALTER TABLE graph_relation UPDATE {assignments} WHERE id = {self._literal(payload['id'])}")
            if existing[0]["relation_type"] == "statement":
                statement_changes = {
                    "subject_entity_id": changes.get("source_node_id"),
                    "object_entity_id": changes.get("target_node_id"),
                    "predicate": changes.get("label"),
                    "description": changes.get("description"),
                    "status": changes.get("status"),
                    "confidence": changes.get("confidence"),
                    "metadata": changes.get("metadata"),
                }
                statement_assignments = ", ".join(
                    f"{key} = {self._literal(value)}" for key, value in statement_changes.items() if value is not None
                )
                if statement_assignments:
                    self.client.command(f"ALTER TABLE statement UPDATE {statement_assignments} WHERE id = {self._literal(payload['id'])}")
            return
        if operation_type == OperationType.DELETE_RELATION:
            relation_id = self._literal(payload["id"])
            relation = result_rows(self.client.query(f"SELECT relation_type FROM graph_relation WHERE id = {relation_id} LIMIT 1"))
            if not relation:
                raise ValueError("graph relation not found")
            self.client.command(f"ALTER TABLE graph_relation UPDATE status = 'deleted' WHERE id = {relation_id}")
            if relation[0]["relation_type"] == "statement":
                self.client.command(f"ALTER TABLE statement UPDATE status = 'invalidated' WHERE id = {relation_id}")
                self.client.command(f"ALTER TABLE knowledge_element UPDATE status = 'invalidated' WHERE id = {relation_id}")
            return
        if operation_type == OperationType.INVALIDATE_STATEMENT:
            self.client.command("ALTER TABLE knowledge_element UPDATE status = 'invalidated' " f"WHERE id = {self._literal(payload['id'])}")
            return
        if operation_type == OperationType.DELETE_NODE:
            node_type = payload["node_type"]
            node_id = self._literal(payload["id"])
            if node_type == "context":
                self.client.command(f"ALTER TABLE context DELETE WHERE id = {node_id}")
            else:
                table = "knowledge_element" if node_type == "knowledge_element" else node_type
                status = "invalidated" if node_type == "knowledge_element" else "deleted"
                self.client.command(f"ALTER TABLE {table} UPDATE status = '{status}' WHERE id = {node_id}")
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
