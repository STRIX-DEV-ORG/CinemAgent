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
