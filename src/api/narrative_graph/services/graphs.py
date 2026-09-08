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
        return NarrativeGraphResponse(id=graph_id, name=request.name, version=1)

    def get_graph(self, graph_id: UUID) -> NarrativeGraphResponse:
        result = self.client.query(
            "SELECT id, name, version, created_at, updated_at FROM narrative_graph WHERE id = {id:UUID} LIMIT 1",
            parameters={"id": graph_id},
        )
        rows = result_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="narrative graph not found")
        return NarrativeGraphResponse(**rows[0])

    def update_graph(self, graph_id: UUID, request: NarrativeGraphUpdate) -> NarrativeGraphResponse:
        self.get_graph(graph_id)
        self.client.command(
            "ALTER TABLE narrative_graph UPDATE name = {name:String}, version = version + 1, "
            "updated_at = now64(3) WHERE id = {id:UUID} SETTINGS mutations_sync = 1",
            parameters={"id": graph_id, "name": request.name},
        )
        return self.get_graph(graph_id)

    def delete_graph(self, graph_id: UUID) -> None:
        """Permanently remove a story and all data owned by its graph.

        Tables that only reference nodes are deleted first while their parent
        IDs are still available for the ClickHouse subqueries.
        """
        self.get_graph(graph_id)
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
        self.client.command(
            "ALTER TABLE narrative_graph DELETE WHERE id = {graph_id:UUID} SETTINGS mutations_sync = 1",
            parameters=parameters,
        )
