"""Checkpointed event projector for the narrative graph read models.

The projector is deliberately at-least-once: every projection row is a
versioned replacement keyed by the source event ordering, so replaying an
event is safe.  The legacy tables remain untouched during the cutover.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from .common import result_rows


_NODE_CREATES = {
    "create_entity": "entity",
    "create_event": "event",
    "create_context": "context",
    "create_knowledge_element": "knowledge_element",
    "create_statement": "statement",
    "create_time": "time",
}


class NarrativeProjectionService:
    projector_name = "narrative-current-v1"

    def __init__(self, client: Any) -> None:
        self.client = client
        self.intelligence: Any | None = None

    def _checkpoint(self, graph_id: UUID) -> tuple[datetime, str]:
        rows = result_rows(self.client.query(
            "SELECT argMax(cursor_at, updated_at) AS cursor_at, argMax(cursor_event_id, updated_at) AS cursor_event_id "
            "FROM narrative_projection_checkpoint WHERE projector = {projector:String} AND graph_id = {graph_id:UUID}",
            parameters={"projector": self.projector_name, "graph_id": graph_id},
        ))
        row = rows[0] if rows else {}
        return row.get("cursor_at") or datetime(1970, 1, 1), row.get("cursor_event_id") or ""

    def _save_checkpoint(self, graph_id: UUID, cursor_at: datetime, cursor_event_id: str, status: str = "healthy", error: str | None = None) -> None:
        self.client.insert(
            "narrative_projection_checkpoint",
            [[self.projector_name, graph_id, cursor_at, cursor_event_id, status, error]],
            column_names=["projector", "graph_id", "cursor_at", "cursor_event_id", "status", "error"],
        )

    @staticmethod
    def _payload(event: dict[str, Any]) -> dict[str, Any]:
        value = event.get("payload") or {}
        return json.loads(value) if isinstance(value, str) else dict(value)

    @staticmethod
    def _json_safe(value: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(value, default=str))

    @staticmethod
    def _version(event: dict[str, Any]) -> int:
        # Millisecond time plus 20 random ULID bits gives a stable, practical
        # total order inside ClickHouse's UInt64 ReplacingMergeTree version.
        event_id = str(event["event_id"])
        return (int(event_id[:13], 16) << 20) | int(event_id[13:18], 16)

    def _current_node(self, graph_id: UUID, node_id: UUID) -> dict[str, Any] | None:
        rows = result_rows(self.client.query(
            "SELECT argMax(node_type, version) AS node_type, argMax(name, version) AS name, "
            "argMax(status, version) AS status, argMax(payload, version) AS payload "
            "FROM narrative_node_current WHERE graph_id = {graph_id:UUID} AND id = {id:UUID}",
            parameters={"graph_id": graph_id, "id": node_id},
        ))
        if not rows or not rows[0].get("node_type"):
            return None
        row = rows[0]
        row["payload"] = self._payload(row)
        return row

    def _current_relation(self, graph_id: UUID, relation_id: UUID) -> dict[str, Any] | None:
        rows = result_rows(self.client.query(
            "SELECT argMax(payload, version) AS payload FROM narrative_relation_current "
            "WHERE graph_id = {graph_id:UUID} AND id = {id:UUID}",
            parameters={"graph_id": graph_id, "id": relation_id},
        ))
        if not rows or not rows[0].get("payload"):
            return None
        return self._payload(rows[0])

    def _project_node(self, event: dict[str, Any], payload: dict[str, Any]) -> None:
        event_type = event["event_type"]
        node_type = _NODE_CREATES.get(event_type) or payload.get("node_type")
        node_id = payload.get("id")
        if event_type == "merge_entity":
            node_type, node_id = "entity", payload.get("source_id")
            payload = {**payload, "status": "merged"}
        if not node_type or not node_id:
            return
        node_id = UUID(str(node_id))
        existing = self._current_node(event["graph_id"], node_id)
        current_payload = existing["payload"] if existing else {}
        if event_type.startswith("update_"):
            current_payload.update(payload.get("changes", {}))
        else:
            current_payload.update(payload)
        deleted = event_type in {"delete_node", "invalidate_statement"}
        status = "invalidated" if event_type == "invalidate_statement" else ("deleted" if deleted else current_payload.get("status", "active"))
        current_payload["id"] = str(node_id)
        self.client.insert(
            "narrative_node_current",
            [[event["graph_id"], node_id, node_type, str(current_payload.get("name", "")), status,
              current_payload, self._version(event), int(deleted), event["event_id"]]],
            column_names=["graph_id", "id", "node_type", "name", "status", "payload", "version", "is_deleted", "event_id"],
        )
        if self.intelligence and not deleted:
            self.intelligence.index_projection_node(event["graph_id"], node_type, node_id, current_payload, self._version(event))

    def _project_relation(self, event: dict[str, Any], payload: dict[str, Any]) -> None:
        event_type = event["event_type"]
        if event_type not in {"create_relation", "update_relation", "delete_relation"}:
            return
        relation_id = UUID(str(payload["id"]))
        changes = payload.get("changes", {})
        base = self._current_relation(event["graph_id"], relation_id) or {}
        base.update(payload)
        base.update(changes)
        deleted = event_type == "delete_relation"
        self.client.insert(
            "narrative_relation_current",
            [[event["graph_id"], relation_id, UUID(str(base.get("source_node_id", "00000000-0000-0000-0000-000000000000"))),
              UUID(str(base.get("target_node_id", "00000000-0000-0000-0000-000000000000"))),
              str(base.get("relation_type", "related_to")), str(base.get("label", "")),
              "deleted" if deleted else str(base.get("status", "active")), base, self._version(event), int(deleted), event["event_id"]]],
            column_names=["graph_id", "id", "source_node_id", "target_node_id", "relation_type", "label", "status", "payload", "version", "is_deleted", "event_id"],
        )

    def _project_membership(self, event: dict[str, Any], payload: dict[str, Any]) -> None:
        if event["event_type"] != "link_node_to_chapter":
            return
        self.client.insert(
            "narrative_membership_current",
            [[event["graph_id"], UUID(str(payload["chapter_id"])), UUID(str(payload["node_id"])), payload["node_type"],
              self._version(event), 0, event["event_id"]]],
            column_names=["graph_id", "chapter_id", "node_id", "node_type", "version", "is_deleted", "event_id"],
        )

    def _project_chapter(self, event: dict[str, Any], payload: dict[str, Any]) -> None:
        if not event["event_type"].startswith("chapter_") or not event.get("chapter_id"):
            return
        deleted = event["event_type"] == "chapter_deleted"
        # Chapter events include full snapshots; legacy events without a snapshot
        # are intentionally ignored and are handled by the bootstrap endpoint.
        if not payload.get("document_json") and not deleted:
            return
        self.client.insert(
            "narrative_chapter_current",
            [[event["graph_id"], event["chapter_id"], str(payload.get("title", "Untitled chapter")), int(payload.get("sequence", 0)),
              str(payload.get("document_json", "{}")), str(payload.get("plain_text", "")), int(payload.get("revision", event.get("version", 1))),
              int(deleted), event["event_id"]]],
            column_names=["graph_id", "id", "title", "sequence", "document_json", "plain_text", "revision", "is_deleted", "event_id"],
        )
        if self.intelligence and not deleted:
            self.intelligence.index_chapter_snapshot(event["graph_id"], event["chapter_id"], payload)

    def project_graph(self, graph_id: UUID, limit: int = 1000) -> dict[str, Any]:
        cursor_at, cursor_event_id = self._checkpoint(graph_id)
        events = result_rows(self.client.query(
            "SELECT event_id, graph_id, chapter_id, event_type, version, payload, occurred_at FROM narrative_event "
            "WHERE graph_id = {graph_id:UUID} AND (occurred_at, event_id) > ({cursor_at:DateTime64(3)}, {cursor_event_id:String}) "
            "ORDER BY occurred_at, event_id LIMIT {limit:UInt32}",
            parameters={"graph_id": graph_id, "cursor_at": cursor_at, "cursor_event_id": cursor_event_id, "limit": limit},
        ))
        if not events:
            return {"graph_id": str(graph_id), "projected": 0, "status": "healthy"}
        try:
            for event in events:
                payload = self._payload(event)
                self._project_chapter(event, payload)
                self._project_node(event, payload)
                self._project_relation(event, payload)
                self._project_membership(event, payload)
            last = events[-1]
            self._save_checkpoint(graph_id, last["occurred_at"], last["event_id"])
            self.refresh_health(graph_id, last["event_id"])
            return {"graph_id": str(graph_id), "projected": len(events), "status": "healthy"}
        except Exception as error:
            self._save_checkpoint(graph_id, cursor_at, cursor_event_id, "failed", str(error))
            raise

    def project_pending(self) -> list[dict[str, Any]]:
        rows = result_rows(self.client.query("SELECT DISTINCT graph_id FROM narrative_event ORDER BY graph_id"))
        return [self.project_graph(row["graph_id"]) for row in rows]

    def parity(self, graph_id: UUID) -> dict[str, Any]:
        """Compare active legacy and projected identities before read cutover."""
        checks: dict[str, tuple[str, str]] = {
            "chapters": ("SELECT id FROM story_chapter WHERE graph_id = {graph_id:UUID}", "SELECT id FROM narrative_chapter_current WHERE graph_id = {graph_id:UUID}"),
            "nodes": ("SELECT id FROM entity WHERE graph_id = {graph_id:UUID} UNION ALL SELECT id FROM event WHERE graph_id = {graph_id:UUID} UNION ALL SELECT id FROM context WHERE graph_id = {graph_id:UUID} UNION ALL SELECT id FROM knowledge_element WHERE graph_id = {graph_id:UUID}", "SELECT id FROM narrative_node_current WHERE graph_id = {graph_id:UUID}"),
            "relations": ("SELECT id FROM graph_relation WHERE graph_id = {graph_id:UUID}", "SELECT id FROM narrative_relation_current WHERE graph_id = {graph_id:UUID}"),
            "memberships": ("SELECT node_id AS id FROM chapter_node WHERE graph_id = {graph_id:UUID}", "SELECT node_id AS id FROM narrative_membership_current WHERE graph_id = {graph_id:UUID}"),
        }
        details: dict[str, Any] = {}
        for name, (legacy, projected) in checks.items():
            legacy_ids = {str(row["id"]) for row in result_rows(self.client.query(legacy, parameters={"graph_id": graph_id}))}
            projected_ids = {str(row["id"]) for row in result_rows(self.client.query(projected, parameters={"graph_id": graph_id}))}
            details[name] = {"legacy": len(legacy_ids), "projected": len(projected_ids), "missing": sorted(legacy_ids - projected_ids)[:20], "extra": sorted(projected_ids - legacy_ids)[:20]}
        passed = all(not item["missing"] for item in details.values())
        status = "passed" if passed else "failed"
        self.client.insert("narrative_projection_rollout", [[graph_id, 0, status, details]], column_names=["graph_id", "projected_reads_enabled", "parity_status", "parity_details"])
        return {"graph_id": str(graph_id), "status": status, "checks": details}

    def set_projected_reads(self, graph_id: UUID, enabled: bool) -> dict[str, Any]:
        report = self.parity(graph_id)
        if enabled and report["status"] != "passed":
            raise ValueError("projected reads require a passing parity report")
        self.client.insert("narrative_projection_rollout", [[graph_id, int(enabled), report["status"], report["checks"]]], column_names=["graph_id", "projected_reads_enabled", "parity_status", "parity_details"])
        return {"graph_id": str(graph_id), "projected_reads_enabled": enabled, "parity_status": report["status"]}

    def reads_enabled(self, graph_id: UUID) -> bool:
        rows = result_rows(self.client.query("SELECT argMax(projected_reads_enabled, updated_at) AS enabled FROM narrative_projection_rollout WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id}))
        return bool(rows and rows[0].get("enabled"))

    def rebuild(self, graph_id: UUID) -> dict[str, Any]:
        """Delete only derived rows, seed legacy state once, then replay events."""
        for table in ("narrative_chapter_current", "narrative_node_current", "narrative_relation_current", "narrative_membership_current", "story_health_snapshot"):
            self.client.command(f"ALTER TABLE {table} DELETE WHERE graph_id = {{graph_id:UUID}} SETTINGS mutations_sync = 1", parameters={"graph_id": graph_id})
        self.client.command("ALTER TABLE narrative_projection_checkpoint DELETE WHERE projector = {projector:String} AND graph_id = {graph_id:UUID} SETTINGS mutations_sync = 1", parameters={"projector": self.projector_name, "graph_id": graph_id})
        counts = self.bootstrap_from_legacy(graph_id)
        while self.project_graph(graph_id, limit=10_000)["projected"]:
            pass
        return {"status": "completed", "seeded": counts, "parity": self.parity(graph_id)}

    def bootstrap_from_legacy(self, graph_id: UUID) -> dict[str, int]:
        """Seed read models from existing tables before the projected-read cutover."""
        version, event_id = 0, "legacy-bootstrap"
        counts = {"chapters": 0, "nodes": 0, "relations": 0, "memberships": 0}
        chapters = result_rows(self.client.query(
            "SELECT id, argMax(title, revision) AS title, argMax(sequence, revision) AS sequence, "
            "argMax(document_json, revision) AS document_json, argMax(plain_text, revision) AS plain_text, max(revision) AS latest_revision "
            "FROM story_chapter WHERE graph_id = {graph_id:UUID} GROUP BY id",
            parameters={"graph_id": graph_id},
        ))
        for row in chapters:
            self.client.insert("narrative_chapter_current", [[graph_id, row["id"], row["title"], row["sequence"], row["document_json"], row["plain_text"], row["latest_revision"], 0, event_id]], column_names=["graph_id", "id", "title", "sequence", "document_json", "plain_text", "revision", "is_deleted", "event_id"])
            counts["chapters"] += 1
        for table, node_type, name_column, status_column in (("entity", "entity", "name", "status"), ("event", "event", "name", "status"), ("context", "context", "name", None), ("knowledge_element", "knowledge_element", "name", "status")):
            rows = result_rows(self.client.query(f"SELECT * FROM {table} WHERE graph_id = {{graph_id:UUID}}", parameters={"graph_id": graph_id}))
            for row in rows:
                status = row.get(status_column, "active") if status_column else "active"
                self.client.insert("narrative_node_current", [[graph_id, row["id"], node_type, str(row.get(name_column, "")), status, self._json_safe(row), version, int(status in {"deleted", "invalidated"}), event_id]], column_names=["graph_id", "id", "node_type", "name", "status", "payload", "version", "is_deleted", "event_id"])
                counts["nodes"] += 1
        for row in result_rows(self.client.query("SELECT * FROM graph_relation WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id})):
            self.client.insert("narrative_relation_current", [[graph_id, row["id"], row["source_node_id"], row["target_node_id"], row["relation_type"], row["label"], row.get("status", "active"), self._json_safe(row), version, int(row.get("status") == "deleted"), event_id]], column_names=["graph_id", "id", "source_node_id", "target_node_id", "relation_type", "label", "status", "payload", "version", "is_deleted", "event_id"])
            counts["relations"] += 1
        for row in result_rows(self.client.query("SELECT graph_id, chapter_id, node_id, node_type FROM chapter_node WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id})):
            self.client.insert("narrative_membership_current", [[graph_id, row["chapter_id"], row["node_id"], row["node_type"], version, 0, event_id]], column_names=["graph_id", "chapter_id", "node_id", "node_type", "version", "is_deleted", "event_id"])
            counts["memberships"] += 1
        self.project_graph(graph_id)
        self.refresh_health(graph_id, event_id)
        return counts

    def status(self, graph_id: UUID) -> dict[str, Any]:
        cursor_at, cursor_event_id = self._checkpoint(graph_id)
        pending = result_rows(self.client.query(
            "SELECT count() AS count FROM narrative_event WHERE graph_id = {graph_id:UUID} "
            "AND (occurred_at, event_id) > ({cursor_at:DateTime64(3)}, {cursor_event_id:String})",
            parameters={"graph_id": graph_id, "cursor_at": cursor_at, "cursor_event_id": cursor_event_id},
        ))
        return {"graph_id": str(graph_id), "projector": self.projector_name, "cursor_at": cursor_at,
                "cursor_event_id": cursor_event_id, "pending_events": int(pending[0]["count"])}

    def refresh_health(self, graph_id: UUID, event_id: str = "") -> None:
        def count(table: str, version_column: str = "version", deleted: str = "is_deleted") -> int:
            rows = result_rows(self.client.query(
                f"SELECT count() AS count FROM (SELECT id, argMax({deleted}, {version_column}) AS deleted "
                f"FROM {table} WHERE graph_id = {{graph_id:UUID}} GROUP BY id HAVING deleted = 0)",
                parameters={"graph_id": graph_id},
            ))
            return int(rows[0]["count"])
        chapters, nodes, relations = count("narrative_chapter_current", "revision"), count("narrative_node_current"), count("narrative_relation_current")
        assumptions = result_rows(self.client.query(
            "SELECT count() AS count FROM (SELECT id, argMax(payload, version) AS payload, argMax(is_deleted, version) AS deleted "
            "FROM narrative_node_current WHERE graph_id = {graph_id:UUID} AND node_type = 'knowledge_element' GROUP BY id) "
            "WHERE deleted = 0 AND JSONExtractString(payload, 'element_type') = 'assumption' "
            "AND JSONExtractString(payload, 'status') NOT IN ('resolved', 'invalidated')",
            parameters={"graph_id": graph_id},
        ))
        evidence = result_rows(self.client.query(
            "SELECT count() AS count FROM evidence AS e INNER JOIN source_segment AS s ON e.source_segment_id = s.id "
            "WHERE s.graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id},
        ))
        evidence_count = int(evidence[0]["count"])
        isolated = max(0, nodes - min(nodes, relations * 2))
        self.client.insert(
            "story_health_snapshot",
            [[graph_id, chapters, nodes, relations, isolated, int(assumptions[0]["count"]), evidence_count,
              min(1.0, evidence_count / max(1, relations)), event_id]],
            column_names=["graph_id", "chapters", "nodes", "relations", "isolated_nodes_estimate", "unresolved_assumptions", "evidence_count", "evidence_coverage", "projection_event_id"],
        )
