"""ClickHouse-native event history, semantic canon, and writer insights."""
from __future__ import annotations

import hashlib
import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from src.rag.embedder import Embedder

from .common import result_rows


def _ulid() -> str:
    """A lexically sortable event ID without adding another infrastructure dependency."""
    return f"{int(time.time() * 1000):013x}{uuid4().hex[:19]}"


class NarrativeIntelligenceService:
    def __init__(self, client: Any, graphs: Any, workspace: Any) -> None:
        self.client = client
        self.graphs = graphs
        self.workspace = workspace
        self._embedder: Embedder | None = None

    def append_event(
        self,
        graph_id: UUID,
        event_type: str,
        *,
        actor_type: str = "system",
        chapter_id: UUID | None = None,
        batch_id: UUID | None = None,
        operation_id: UUID | None = None,
        version: int = 1,
        payload: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        event_id = _ulid()
        self.client.insert(
            "narrative_event",
            [[event_id, graph_id, chapter_id, batch_id, operation_id, event_type, actor_type,
              version, payload or {}, provenance or {}]],
            column_names=["event_id", "graph_id", "chapter_id", "batch_id", "operation_id", "event_type",
                          "actor_type", "version", "payload", "provenance"],
        )
        return event_id

    def events(self, graph_id: UUID, chapter_id: UUID | None = None, limit: int = 100) -> list[dict[str, Any]]:
        self.graphs.get_graph(graph_id)
        clause = "AND chapter_id = {chapter_id:UUID}" if chapter_id else ""
        parameters: dict[str, Any] = {"graph_id": graph_id, "limit": limit}
        if chapter_id:
            parameters["chapter_id"] = chapter_id
        return result_rows(self.client.query(
            "SELECT event_id, graph_id, chapter_id, batch_id, operation_id, event_type, actor_type, version, "
            "payload, provenance, occurred_at FROM narrative_event "
            f"WHERE graph_id = {{graph_id:UUID}} {clause} ORDER BY occurred_at DESC, event_id DESC LIMIT {{limit:UInt32}}",
            parameters=parameters,
        ))

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    def _insert_embedding(self, graph_id: UUID, source_type: str, source_id: str, content: str,
                          chapter_id: UUID | None = None, version: int = 1,
                          metadata: dict[str, Any] | None = None) -> bool:
        content = content.strip()
        if not content:
            return False
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = result_rows(self.client.query(
            "SELECT id FROM narrative_embedding WHERE graph_id = {graph_id:UUID} "
            "AND source_type = {source_type:String} AND source_id = {source_id:String} "
            "AND content_hash = {content_hash:String} AND is_active = 1 LIMIT 1",
            parameters={"graph_id": graph_id, "source_type": source_type, "source_id": source_id, "content_hash": digest},
        ))
        if existing:
            return False
        # Superseded embeddings remain auditable but cannot be retrieved.
        self.client.command(
            "ALTER TABLE narrative_embedding UPDATE is_active = 0 WHERE graph_id = {graph_id:UUID} "
            "AND source_type = {source_type:String} AND source_id = {source_id:String} AND is_active = 1",
            parameters={"graph_id": graph_id, "source_type": source_type, "source_id": source_id},
        )
        self.client.insert(
            "narrative_embedding",
            [[uuid4(), graph_id, chapter_id, source_type, source_id, version, digest, content,
              "text-embedding-004", self.embedder.get_embedding(content), metadata or {}, 1]],
            column_names=["id", "graph_id", "chapter_id", "source_type", "source_id", "source_version",
                          "content_hash", "content", "model", "embedding", "metadata", "is_active"],
        )
        return True

    @staticmethod
    def _chunks(text: str, size: int = 1400, overlap: int = 180) -> list[str]:
        text = text.strip()
        if len(text) <= size:
            return [text] if text else []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + size)
            if end < len(text):
                boundary = text.rfind(" ", start + size // 2, end)
                end = boundary if boundary > start else end
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return chunks

    def index_chapter_snapshot(self, graph_id: UUID, chapter_id: UUID, payload: dict[str, Any]) -> int:
        revision = int(payload.get("revision", 1))
        indexed = 0
        for index, chunk in enumerate(self._chunks(str(payload.get("plain_text", "")))):
            indexed += int(self._insert_embedding(
                graph_id, "chapter", f"{chapter_id}:{index}", chunk, chapter_id, revision,
                {"chapter_id": str(chapter_id), "title": payload.get("title", ""), "sequence": payload.get("sequence", 0), "chunk_index": index},
            ))
        return indexed

    def index_projection_node(self, graph_id: UUID, node_type: str, node_id: UUID,
                              payload: dict[str, Any], version: int) -> bool:
        text = "\n".join(str(payload.get(field) or "") for field in ("name", "description", "content")).strip()
        chapter_id = payload.get("chapter_id")
        return self._insert_embedding(
            graph_id, node_type, str(node_id), text,
            UUID(str(chapter_id)) if chapter_id else None, version,
            {"node_id": str(node_id), "node_type": node_type, "name": payload.get("name", "")},
        )

    def backfill_canon(self, graph_id: UUID) -> dict[str, int]:
        self.graphs.get_graph(graph_id)
        indexed = {"chapter": 0, "entity": 0, "event": 0, "context": 0, "statement": 0, "evidence": 0}
        for chapter in self.workspace.list_chapters(graph_id):
            indexed["chapter"] += self.index_chapter_snapshot(graph_id, chapter.id, {
                "title": chapter.title, "sequence": chapter.sequence, "plain_text": chapter.plain_text, "revision": chapter.revision,
            })
        sources = {
            "entity": ("SELECT id, name, description, content FROM entity WHERE graph_id = {graph_id:UUID} AND status != 'deleted'", None),
            "event": ("SELECT id, name, description, content FROM event WHERE graph_id = {graph_id:UUID} AND status != 'deleted'", None),
            "context": ("SELECT id, name, description, content FROM context WHERE graph_id = {graph_id:UUID}", None),
            "statement": ("SELECT k.id, k.name, k.description, k.content FROM knowledge_element AS k WHERE k.graph_id = {graph_id:UUID} AND k.element_type = 'statement' AND k.status != 'invalidated'", None),
            "evidence": ("SELECT e.id, '' AS name, e.excerpt AS description, '' AS content FROM evidence AS e INNER JOIN source_segment AS s ON e.source_segment_id = s.id WHERE s.graph_id = {graph_id:UUID}", None),
        }
        for source_type, (query, _) in sources.items():
            for row in result_rows(self.client.query(query, parameters={"graph_id": graph_id})):
                text = "\n".join(str(row.get(field) or "") for field in ("name", "description", "content")).strip()
                indexed[source_type] += int(self._insert_embedding(graph_id, source_type, str(row["id"]), text))
        self.append_event(graph_id, "canon_indexed", payload={"indexed": indexed})
        return indexed

    def backfill_legacy_events(self, graph_id: UUID) -> dict[str, int | str]:
        """Seed immutable baseline events for a pre-event-stream story once."""
        self.graphs.get_graph(graph_id)
        existing = result_rows(self.client.query(
            "SELECT count() AS count FROM narrative_event WHERE graph_id = {graph_id:UUID} "
            "AND event_type = 'legacy_baseline'", parameters={"graph_id": graph_id},
        ))
        if int(existing[0]["count"]):
            return {"status": "already_backfilled", "events": 0}
        total = 0
        graph = self.graphs.get_graph(graph_id)
        self.append_event(graph_id, "legacy_baseline", payload={"kind": "story", "name": graph.name})
        total += 1
        for chapter in self.workspace.list_chapters(graph_id):
            self.append_event(graph_id, "legacy_baseline", actor_type="migration", chapter_id=chapter.id,
                              version=chapter.revision, payload={"kind": "chapter", "title": chapter.title,
                                                                   "sequence": chapter.sequence, "plain_text": chapter.plain_text})
            total += 1
        for table, kind, columns in (
            ("entity", "entity", "id, name, type, status, description, content"),
            ("event", "event", "id, name, type, status, description, content"),
            ("context", "context", "id, name, type, description, content"),
            ("knowledge_element", "knowledge_element", "id, name, element_type, status, description, content"),
            ("graph_relation", "relation", "id, source_node_id, target_node_id, relation_type, label, description, status"),
        ):
            for row in result_rows(self.client.query(
                f"SELECT {columns} FROM {table} WHERE graph_id = {{graph_id:UUID}}", parameters={"graph_id": graph_id}
            )):
                operation_id = row.pop("id")
                self.append_event(graph_id, "legacy_baseline", actor_type="migration", operation_id=operation_id,
                                  payload={"kind": kind, **row})
                total += 1
        return {"status": "completed", "events": total}

    def semantic_search(self, graph_id: UUID, query: str, chapter_id: UUID | None = None,
                        source_types: list[str] | None = None, limit: int = 10) -> list[dict[str, Any]]:
        if not query.strip():
            raise HTTPException(status_code=422, detail="query cannot be blank")
        self.graphs.get_graph(graph_id)
        parameters: dict[str, Any] = {"graph_id": graph_id, "vector": self.embedder.get_embedding(query), "limit": limit}
        filters = ["graph_id = {graph_id:UUID}", "is_active = 1"]
        if chapter_id:
            filters.append("chapter_id = {chapter_id:UUID}")
            parameters["chapter_id"] = chapter_id
        if source_types:
            filters.append("source_type IN {source_types:Array(String)}")
            parameters["source_types"] = source_types
        started = time.perf_counter()
        try:
            rows = result_rows(self.client.query(
                "SELECT source_type, source_id, chapter_id, source_version, content, metadata, "
                "cosineDistance(embedding, {vector:Array(Float32)}) AS distance "
                "FROM narrative_embedding WHERE " + " AND ".join(filters) + " "
                "ORDER BY distance ASC LIMIT {limit:UInt32}", parameters=parameters,
            ))
            for row in rows:
                source_id = str(row["source_id"])
                chapter_id = row.get("chapter_id")
                if row["source_type"] == "chapter":
                    row["destination"] = {"kind": "chapter", "chapter_id": str(chapter_id or source_id.split(":", 1)[0])}
                    continue
                memberships = result_rows(self.client.query(
                    "SELECT chapter_id FROM chapter_node WHERE graph_id = {graph_id:UUID} AND node_id = {node_id:UUID} "
                    "ORDER BY created_at LIMIT 1", parameters={"graph_id": graph_id, "node_id": UUID(source_id)}
                ))
                target_chapter = str(chapter_id) if chapter_id else (str(memberships[0]["chapter_id"]) if memberships else None)
                row["destination"] = {"kind": "node", "node_id": source_id, "chapter_id": target_chapter,
                                      "node_type": row["source_type"]}
            self._record_query("semantic_search", graph_id, started, len(rows))
            return rows
        except Exception as error:
            self._record_query("semantic_search", graph_id, started, 0, str(error))
            raise

    def _record_query(self, operation: str, graph_id: UUID | None, started: float, rows: int, error: str = "") -> None:
        """Best-effort telemetry; observability must never break writer work."""
        try:
            self.client.insert("narrative_query_telemetry", [[operation, graph_id or UUID(int=0), int((time.perf_counter() - started) * 1000), int(not error), error[:1000], rows]],
                               column_names=["operation", "graph_id", "duration_ms", "success", "error", "rows_returned"])
        except Exception:
            pass

    def story_health(self, graph_id: UUID) -> dict[str, Any]:
        self.graphs.get_graph(graph_id)
        snapshot = result_rows(self.client.query(
            "SELECT chapters, nodes, relations, isolated_nodes_estimate, unresolved_assumptions, evidence_count, evidence_coverage "
            "FROM story_health_snapshot WHERE graph_id = {graph_id:UUID} ORDER BY calculated_at DESC LIMIT 1",
            parameters={"graph_id": graph_id},
        ))
        if snapshot:
            result = dict(snapshot[0])
            result["graph_id"] = graph_id
            return result
        def count(query: str) -> int:
            return int(result_rows(self.client.query(query, parameters={"graph_id": graph_id}))[0]["count"])
        entity_count = count("SELECT count() AS count FROM entity WHERE graph_id = {graph_id:UUID} AND status != 'deleted'")
        event_count = count("SELECT count() AS count FROM event WHERE graph_id = {graph_id:UUID} AND status != 'deleted'")
        context_count = count("SELECT count() AS count FROM context WHERE graph_id = {graph_id:UUID}")
        relation_count = count("SELECT count() AS count FROM graph_relation WHERE graph_id = {graph_id:UUID} AND status != 'deleted'")
        unresolved = count("SELECT count() AS count FROM knowledge_element WHERE graph_id = {graph_id:UUID} AND element_type = 'assumption' AND status NOT IN ('invalidated', 'resolved')")
        evidence_count = count("SELECT count() AS count FROM evidence AS e INNER JOIN source_segment AS s ON e.source_segment_id = s.id WHERE s.graph_id = {graph_id:UUID}")
        nodes = entity_count + event_count + context_count
        isolated = max(0, nodes - min(nodes, relation_count * 2))
        chapters = self.workspace.list_chapters(graph_id)
        return {"graph_id": graph_id, "chapters": len(chapters), "nodes": nodes, "relations": relation_count,
                "isolated_nodes_estimate": isolated, "unresolved_assumptions": unresolved,
                "evidence_count": evidence_count,
                "evidence_coverage": round(min(1.0, evidence_count / max(1, event_count + relation_count)), 3)}

    def character_presence(self, graph_id: UUID) -> list[dict[str, Any]]:
        chapters = {str(chapter.id): chapter for chapter in self.workspace.list_chapters(graph_id)}
        rows = result_rows(self.client.query(
            "SELECT c.chapter_id, e.id AS entity_id, e.name, e.type FROM chapter_node AS c "
            "INNER JOIN entity AS e ON c.node_id = e.id WHERE c.graph_id = {graph_id:UUID} "
            "AND c.node_type = 'entity' AND e.status != 'deleted' ORDER BY c.chapter_id, e.name",
            parameters={"graph_id": graph_id},
        ))
        return [{"chapter_id": str(row["chapter_id"]), "chapter_title": chapters.get(str(row["chapter_id"])).title if str(row["chapter_id"]) in chapters else "Unknown chapter",
                 "chapter_sequence": chapters.get(str(row["chapter_id"])).sequence if str(row["chapter_id"]) in chapters else 0,
                 "entity_id": str(row["entity_id"]), "name": row["name"], "type": row["type"]} for row in rows]

    def relation_timeline(self, graph_id: UUID) -> list[dict[str, Any]]:
        chapters = {str(chapter.id): chapter for chapter in self.workspace.list_chapters(graph_id)}
        rows = result_rows(self.client.query(
            "SELECT c.chapter_id, r.id, r.source_node_id, r.target_node_id, r.relation_type, r.label, r.description, r.status "
            "FROM chapter_node AS c INNER JOIN graph_relation AS r ON c.node_id = r.id "
            "WHERE c.graph_id = {graph_id:UUID} AND c.node_type = 'relation' AND r.status != 'deleted' "
            "ORDER BY c.chapter_id, r.id", parameters={"graph_id": graph_id},
        ))
        return [{**row, "id": str(row["id"]), "chapter_id": str(row["chapter_id"]),
                 "source_node_id": str(row["source_node_id"]), "target_node_id": str(row["target_node_id"]),
                 "chapter_title": chapters.get(str(row["chapter_id"])).title if str(row["chapter_id"]) in chapters else "Unknown chapter",
                 "chapter_sequence": chapters.get(str(row["chapter_id"])).sequence if str(row["chapter_id"]) in chapters else 0} for row in rows]

    def metrics(self, graph_id: UUID) -> dict[str, Any]:
        activity = result_rows(self.client.query(
            "SELECT day, event_type, sum(event_count) AS event_count FROM story_activity_daily "
            "WHERE graph_id = {graph_id:UUID} GROUP BY day, event_type ORDER BY day DESC LIMIT 30",
            parameters={"graph_id": graph_id},
        ))
        runs = result_rows(self.client.query(
            "SELECT agent_group, status, sum(run_count) AS count FROM agent_run_daily WHERE graph_id = {graph_id:UUID} "
            "GROUP BY agent_group, status ORDER BY agent_group, status", parameters={"graph_id": graph_id},
        ))
        embeddings = result_rows(self.client.query(
            "SELECT source_type, count() AS count FROM narrative_embedding WHERE graph_id = {graph_id:UUID} GROUP BY source_type",
            parameters={"graph_id": graph_id},
        ))
        return {"activity": activity, "agent_runs": runs, "embeddings": embeddings}

    def diagnostics(self) -> dict[str, Any]:
        """Developer-only ClickHouse service health, without relying on Cloud system-table grants."""
        telemetry = result_rows(self.client.query(
            "SELECT operation, count() AS calls, round(avg(duration_ms), 1) AS average_ms, "
            "max(duration_ms) AS max_ms, sum(1 - success) AS failures FROM narrative_query_telemetry "
            "WHERE occurred_at >= now64(3) - INTERVAL 24 HOUR GROUP BY operation ORDER BY average_ms DESC"
        ))
        projections = result_rows(self.client.query(
            "SELECT projector, status, count() AS stories, min(updated_at) AS oldest_checkpoint "
            "FROM narrative_projection_checkpoint GROUP BY projector, status"
        ))
        storage = result_rows(self.client.query(
            "SELECT table, sum(rows) AS rows, sum(bytes_on_disk) AS bytes_on_disk FROM system.parts "
            "WHERE active AND database = currentDatabase() AND table IN ('narrative_event', 'narrative_embedding', 'narrative_query_telemetry') "
            "GROUP BY table ORDER BY table"
        ))
        return {"query_telemetry_24h": telemetry, "projection_health": projections, "storage": storage,
                "retention": {"narrative_query_telemetry_days": 30}}
