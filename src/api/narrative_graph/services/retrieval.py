"""Focused narrative graph reads for agents and the writer UI."""
from typing import Any
from uuid import UUID

from ..models import SubgraphQuery
from .common import result_rows
from .graphs import GraphService


class SubgraphService:
    def __init__(self, client: Any, graphs: GraphService) -> None:
        self.client = client
        self.graphs = graphs

    def query_subgraph(self, graph_id: UUID, request: SubgraphQuery) -> dict[str, Any]:
        self.graphs.get_graph(graph_id)
        parameters: dict[str, Any] = {"graph_id": graph_id, "limit": request.limit}
        entity_filter = ""
        event_filter = ""
        if request.entity_ids:
            parameters["entity_ids"] = request.entity_ids
            entity_filter = " AND id IN {entity_ids:Array(UUID)}"
        if request.event_ids:
            parameters["event_ids"] = request.event_ids
            event_filter = " AND id IN {event_ids:Array(UUID)}"
        entities = result_rows(self.client.query(
            "SELECT id, name, type, status, confidence, aliases, metadata FROM entity "
            f"WHERE graph_id = {{graph_id:UUID}}{entity_filter} LIMIT {{limit:UInt32}}", parameters=parameters))
        events = result_rows(self.client.query(
            "SELECT id, time_id, name, type, status, description, confidence, metadata FROM event "
            f"WHERE graph_id = {{graph_id:UUID}}{event_filter} LIMIT {{limit:UInt32}}", parameters=parameters))
        elements = result_rows(self.client.query(
            "SELECT id, time_id, context_id, element_type, origin, status, confidence, metadata FROM knowledge_element "
            "WHERE graph_id = {graph_id:UUID} AND status != 'invalidated' LIMIT {limit:UInt32}", parameters=parameters))
        statements = result_rows(self.client.query(
            "SELECT s.id, s.subject_entity_id, s.predicate, s.object_entity_id FROM statement AS s "
            "INNER JOIN knowledge_element AS k ON s.id = k.id "
            "WHERE k.graph_id = {graph_id:UUID} AND k.status != 'invalidated' LIMIT {limit:UInt32}", parameters=parameters))
        evidence: list[dict[str, Any]] = []
        if request.include_evidence:
            evidence = result_rows(self.client.query(
                "SELECT e.id, e.source_segment_id, e.excerpt, e.confidence, e.start_offset, e.end_offset "
                "FROM evidence AS e INNER JOIN source_segment AS s ON e.source_segment_id = s.id "
                "WHERE s.graph_id = {graph_id:UUID} LIMIT {limit:UInt32}", parameters=parameters))
        return {"graph_id": graph_id, "viewpoint_entity_id": request.viewpoint_entity_id, "entities": entities,
                "events": events, "knowledge_elements": elements, "statements": statements, "evidence": evidence}
