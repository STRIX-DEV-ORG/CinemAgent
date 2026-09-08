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
            "SELECT id, name, type, status, description, content, confidence, aliases, metadata FROM entity "
            f"WHERE graph_id = {{graph_id:UUID}} AND status != 'deleted'{entity_filter} LIMIT {{limit:UInt32}}", parameters=parameters))
        events = result_rows(self.client.query(
            "SELECT id, time_id, name, type, status, description, content, confidence, metadata FROM event "
            f"WHERE graph_id = {{graph_id:UUID}} AND status != 'deleted'{event_filter} LIMIT {{limit:UInt32}}", parameters=parameters))
        contexts = result_rows(self.client.query(
            "SELECT id, name, type, description, content, holder_entity_id, confidence, metadata FROM context "
            "WHERE graph_id = {graph_id:UUID} LIMIT {limit:UInt32}", parameters=parameters))
        elements = result_rows(self.client.query(
            "SELECT id, time_id, context_id, element_type, name, description, content, origin, status, confidence, metadata FROM knowledge_element "
            "WHERE graph_id = {graph_id:UUID} AND status != 'invalidated' LIMIT {limit:UInt32}", parameters=parameters))
        statements = result_rows(self.client.query(
            "SELECT s.id, s.subject_entity_id, s.predicate, s.object_entity_id, s.description, s.status, s.confidence, s.metadata FROM statement AS s "
            "INNER JOIN knowledge_element AS k ON s.id = k.id "
            "WHERE k.graph_id = {graph_id:UUID} AND k.status != 'invalidated' LIMIT {limit:UInt32}", parameters=parameters))
        relations = result_rows(self.client.query(
            "SELECT id, source_node_id, target_node_id, relation_type, label, description, status, confidence, metadata "
            "FROM graph_relation WHERE graph_id = {graph_id:UUID} AND status != 'deleted' LIMIT {limit:UInt32}",
            parameters=parameters,
        ))
        if request.chapter_id:
            memberships = result_rows(self.client.query(
                "SELECT node_id, node_type FROM chapter_node WHERE graph_id = {graph_id:UUID} "
                "AND chapter_id = {chapter_id:UUID}",
                parameters={"graph_id": graph_id, "chapter_id": request.chapter_id},
            ))
            ids_by_type: dict[str, set[str]] = {
                "entity": set(), "event": set(), "context": set(), "knowledge_element": set(), "relation": set()
            }
            for membership in memberships:
                ids_by_type[membership["node_type"]].add(str(membership["node_id"]))
            entities = [item for item in entities if str(item["id"]) in ids_by_type["entity"]]
            events = [item for item in events if str(item["id"]) in ids_by_type["event"]]
            contexts = [item for item in contexts if str(item["id"]) in ids_by_type["context"]]
            elements = [item for item in elements if str(item["id"]) in ids_by_type["knowledge_element"]]
            statements = [item for item in statements if str(item["id"]) in ids_by_type["knowledge_element"]]
            relations = [item for item in relations if str(item["id"]) in ids_by_type["relation"]]
        evidence: list[dict[str, Any]] = []
        if request.include_evidence:
            evidence = result_rows(self.client.query(
                "SELECT e.id, e.source_segment_id, e.excerpt, e.confidence, e.start_offset, e.end_offset "
                "FROM evidence AS e INNER JOIN source_segment AS s ON e.source_segment_id = s.id "
                "WHERE s.graph_id = {graph_id:UUID} LIMIT {limit:UInt32}", parameters=parameters))
        return {"graph_id": graph_id, "viewpoint_entity_id": request.viewpoint_entity_id, "entities": entities,
                "contexts": contexts,
                "events": events, "knowledge_elements": elements, "statements": statements, "relations": relations, "evidence": evidence}
