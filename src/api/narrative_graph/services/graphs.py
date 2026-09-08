"""Narrative graph lifecycle persistence."""
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from ..models import NarrativeGraphCreate, NarrativeGraphResponse, NarrativeGraphUpdate
from .common import result_rows


class GraphService:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.intelligence: Any | None = None

    def create_graph(self, request: NarrativeGraphCreate) -> NarrativeGraphResponse:
        graph_id = uuid4()
        self.client.insert("narrative_graph", [[graph_id, request.name]], column_names=["id", "name"])
        chapter_id = uuid4()
        document = {"type": "doc", "content": [{"type": "paragraph"}]}
        self.client.insert(
            "story_chapter",
            [[chapter_id, graph_id, "Chapter 1", 1, json.dumps(document), "", 1]],
            column_names=["id", "graph_id", "title", "sequence", "document_json", "plain_text", "revision"],
        )
        response = NarrativeGraphResponse(id=graph_id, name=request.name, version=1)
        if self.intelligence:
            self.intelligence.append_event(graph_id, "story_created", actor_type="writer", payload={"id": str(graph_id), "name": request.name})
            self.intelligence.append_event(graph_id, "chapter_created", actor_type="writer", chapter_id=chapter_id, version=1, payload={"id": str(chapter_id), "title": "Chapter 1", "sequence": 1, "document_json": json.dumps(document), "plain_text": "", "revision": 1})
        return response

    def get_graph(self, graph_id: UUID) -> NarrativeGraphResponse:
        result = self.client.query(
            "SELECT id, name, version, created_at, updated_at FROM narrative_graph WHERE id = {id:UUID} LIMIT 1",
            parameters={"id": graph_id},
        )
        rows = result_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="narrative graph not found")
        lifecycle = result_rows(self.client.query(
            "SELECT argMax(deleted_at, updated_at) AS deleted_at, argMax(purged_at, updated_at) AS purged_at "
            "FROM narrative_story_deletion WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id}
        ))
        if lifecycle and (lifecycle[0].get("deleted_at") or lifecycle[0].get("purged_at")):
            raise HTTPException(status_code=404, detail="story is deleted")
        return NarrativeGraphResponse(**rows[0])

    def update_graph(self, graph_id: UUID, request: NarrativeGraphUpdate) -> NarrativeGraphResponse:
        self.get_graph(graph_id)
        self.client.command(
            "ALTER TABLE narrative_graph UPDATE name = {name:String}, version = version + 1, "
            "updated_at = now64(3) WHERE id = {id:UUID} SETTINGS mutations_sync = 1",
            parameters={"id": graph_id, "name": request.name},
        )
        response = self.get_graph(graph_id)
        if self.intelligence:
            self.intelligence.append_event(graph_id, "story_updated", actor_type="writer", version=response.version, payload={"id": str(graph_id), "name": response.name})
        return response

    def delete_graph(self, graph_id: UUID) -> None:
        """Hide a story now and retain it for the configured recovery window."""
        self.get_graph(graph_id)
        event_id = ""
        if self.intelligence:
            event_id = self.intelligence.append_event(graph_id, "story_deleted", actor_type="writer", payload={"id": str(graph_id), "recovery_days": 30})
        self.client.insert("narrative_story_deletion", [[graph_id, None, None, None, None, event_id]], column_names=["graph_id", "deleted_at", "purge_after", "restored_at", "purged_at", "event_id"])
        self.client.command("ALTER TABLE narrative_story_deletion UPDATE deleted_at = now64(3), purge_after = now64(3) + INTERVAL 30 DAY WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id})

    def restore_graph(self, graph_id: UUID) -> None:
        rows = result_rows(self.client.query("SELECT count() AS count FROM narrative_graph WHERE id = {graph_id:UUID}", parameters={"graph_id": graph_id}))
        if not int(rows[0]["count"]):
            raise HTTPException(status_code=404, detail="narrative graph not found")
        event_id = self.intelligence.append_event(graph_id, "story_restored", actor_type="writer", payload={"id": str(graph_id)}) if self.intelligence else ""
        self.client.insert("narrative_story_deletion", [[graph_id, None, None, None, None, event_id]], column_names=["graph_id", "deleted_at", "purge_after", "restored_at", "purged_at", "event_id"])
        self.client.command("ALTER TABLE narrative_story_deletion UPDATE deleted_at = NULL, purge_after = NULL, restored_at = now64(3) WHERE graph_id = {graph_id:UUID}", parameters={"graph_id": graph_id})

    def purge_graph(self, graph_id: UUID) -> None:
        """Irreversibly purge an expired tombstone and its large derived data."""
        parameters = {"graph_id": graph_id}
        dependent_deletes = [
            "ALTER TABLE statement DELETE WHERE subject_entity_id IN (SELECT id FROM entity WHERE graph_id = {graph_id:UUID}) OR object_entity_id IN (SELECT id FROM entity WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
            "ALTER TABLE attribute DELETE WHERE owner_entity_id IN (SELECT id FROM entity WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
            "ALTER TABLE event_participant DELETE WHERE event_id IN (SELECT id FROM event WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
            "ALTER TABLE event_effect DELETE WHERE event_id IN (SELECT id FROM event WHERE graph_id = {graph_id:UUID}) OR knowledge_element_id IN (SELECT id FROM knowledge_element WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
            "ALTER TABLE event_relation DELETE WHERE source_event_id IN (SELECT id FROM event WHERE graph_id = {graph_id:UUID}) OR target_event_id IN (SELECT id FROM event WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
            "ALTER TABLE element_evidence DELETE WHERE evidence_id IN (SELECT id FROM evidence WHERE source_segment_id IN (SELECT id FROM source_segment WHERE graph_id = {graph_id:UUID})) SETTINGS mutations_sync = 1",
            "ALTER TABLE evidence DELETE WHERE source_segment_id IN (SELECT id FROM source_segment WHERE graph_id = {graph_id:UUID}) SETTINGS mutations_sync = 1",
        ]
        for statement in dependent_deletes:
            self.client.command(statement, parameters=parameters)
        graph_tables = [
            "agent_artifact", "agent_run", "chapter_analysis_proposal", "chapter_analysis_run", "chapter_node",
            "story_chapter", "graph_operation", "operation_batch", "source_segment", "graph_relation",
            "knowledge_element", "event", "context", "time", "entity",
        ]
        for table in graph_tables:
            self.client.command(
                f"ALTER TABLE {table} DELETE WHERE graph_id = {{graph_id:UUID}} SETTINGS mutations_sync = 1",
                parameters=parameters,
            )
        self.client.command("ALTER TABLE narrative_embedding DELETE WHERE graph_id = {graph_id:UUID} SETTINGS mutations_sync = 1", parameters=parameters)
        self.client.command("ALTER TABLE narrative_graph DELETE WHERE id = {graph_id:UUID} SETTINGS mutations_sync = 1", parameters=parameters)
        self.client.insert("narrative_story_deletion", [[graph_id, None, None, None, None, "purged"]], column_names=["graph_id", "deleted_at", "purge_after", "restored_at", "purged_at", "event_id"])
        self.client.command("ALTER TABLE narrative_story_deletion UPDATE purged_at = now64(3) WHERE graph_id = {graph_id:UUID}", parameters=parameters)

    def purge_expired(self) -> int:
        rows = result_rows(self.client.query("SELECT graph_id FROM narrative_story_deletion WHERE purge_after <= now64(3) AND purged_at IS NULL"))
        for row in rows:
            self.purge_graph(row["graph_id"])
        return len(rows)
