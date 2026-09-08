"""Writer workspace persistence, document revisions, and reviewable chapter analysis."""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from ..models import (
    ChapterAnalysisResponse,
    ChapterCreate,
    ChapterDocumentUpdate,
    ChapterResponse,
    ChapterUpdate,
)
from .common import result_rows
from .graphs import GraphService


class WorkspaceService:
    def __init__(self, client: Any, graphs: GraphService) -> None:
        self.client = client
        self.graphs = graphs

    @staticmethod
    def _chapter(row: dict[str, Any]) -> ChapterResponse:
        row = dict(row)
        row["document"] = json.loads(row.pop("document_json"))
        return ChapterResponse(**row)

    def list_chapters(self, graph_id: UUID) -> list[ChapterResponse]:
        self.graphs.get_graph(graph_id)
        result = self.client.query(
            "SELECT id, graph_id, title, sequence, document_json, plain_text, revision, created_at, updated_at "
            "FROM story_chapter FINAL WHERE graph_id = {graph_id:UUID} ORDER BY sequence, id",
            parameters={"graph_id": graph_id},
        )
        return [self._chapter(row) for row in result_rows(result)]

    def get_chapter(self, graph_id: UUID, chapter_id: UUID) -> ChapterResponse:
        result = self.client.query(
            "SELECT id, graph_id, title, sequence, document_json, plain_text, revision, created_at, updated_at "
            "FROM story_chapter FINAL WHERE graph_id = {graph_id:UUID} AND id = {chapter_id:UUID} LIMIT 1",
            parameters={"graph_id": graph_id, "chapter_id": chapter_id},
        )
        rows = result_rows(result)
        if not rows:
            raise HTTPException(status_code=404, detail="chapter not found")
        return self._chapter(rows[0])

    def create_chapter(self, graph_id: UUID, request: ChapterCreate) -> ChapterResponse:
        chapters = self.list_chapters(graph_id)
        chapter_id = uuid4()
        document = {"type": "doc", "content": [{"type": "paragraph"}]}
        sequence = len(chapters) + 1
        self.client.insert(
            "story_chapter",
            [[chapter_id, graph_id, request.title, sequence, json.dumps(document), "", 1]],
            column_names=["id", "graph_id", "title", "sequence", "document_json", "plain_text", "revision"],
        )
        return self.get_chapter(graph_id, chapter_id)

    def delete_chapter(self, graph_id: UUID, chapter_id: UUID) -> None:
        chapters = self.list_chapters(graph_id)
        self.get_chapter(graph_id, chapter_id)
        if len(chapters) <= 1:
            raise HTTPException(status_code=422, detail="a story must retain at least one chapter")
        self.client.command(
            "ALTER TABLE story_chapter DELETE WHERE graph_id = {graph_id:UUID} "
            "AND id = {chapter_id:UUID} SETTINGS mutations_sync = 1",
            parameters={"graph_id": graph_id, "chapter_id": chapter_id},
        )

    def update_chapter(self, graph_id: UUID, chapter_id: UUID, request: ChapterUpdate) -> ChapterResponse:
        chapter = self.get_chapter(graph_id, chapter_id)
        title = request.title if request.title is not None else chapter.title
        sequence = request.sequence if request.sequence is not None else chapter.sequence
        self.client.insert(
            "story_chapter",
            [[chapter.id, graph_id, title, sequence, json.dumps(chapter.document), chapter.plain_text, chapter.revision + 1]],
            column_names=["id", "graph_id", "title", "sequence", "document_json", "plain_text", "revision"],
        )
        return self.get_chapter(graph_id, chapter_id)

    def update_document(self, graph_id: UUID, chapter_id: UUID, request: ChapterDocumentUpdate) -> ChapterResponse:
        chapter = self.get_chapter(graph_id, chapter_id)
        if request.revision != chapter.revision:
            raise HTTPException(status_code=409, detail={"message": "chapter revision conflict", "chapter": chapter.model_dump(mode="json")})
        self.client.insert(
            "story_chapter",
            [[chapter.id, graph_id, chapter.title, chapter.sequence, json.dumps(request.document), request.plain_text, chapter.revision + 1]],
            column_names=["id", "graph_id", "title", "sequence", "document_json", "plain_text", "revision"],
        )
        return self.get_chapter(graph_id, chapter_id)

    def start_analysis(self, graph_id: UUID, chapter_id: UUID) -> ChapterAnalysisResponse:
        chapter = self.get_chapter(graph_id, chapter_id)
        run_id = uuid4()
        self.client.insert(
            "chapter_analysis_run",
            [[run_id, graph_id, chapter_id, chapter.revision, "completed", None]],
            column_names=["id", "graph_id", "chapter_id", "chapter_revision", "status", "error"],
        )
        self._create_proposals(run_id, graph_id, chapter)
        return ChapterAnalysisResponse(id=run_id, graph_id=graph_id, chapter_id=chapter_id, chapter_revision=chapter.revision, status="completed")

    def _create_proposals(self, run_id: UUID, graph_id: UUID, chapter: ChapterResponse) -> None:
        """Produce reviewable graph operations from the current chapter draft.

        This deterministic fallback is deliberately conservative: it proposes
        named entities, clear actions, and explicit scene settings rather than
        silently writing a graph from every capitalized word.
        """
        existing_entities = {
            str(row["name"]).casefold(): str(row["id"])
            for row in result_rows(
                self.client.query(
                    "SELECT id, name FROM entity WHERE graph_id = {graph_id:UUID} AND status != 'deleted'",
                    parameters={"graph_id": graph_id},
                )
            )
        }
        existing_names = set(existing_entities)
        known_entity_ids = dict(existing_entities)
        seen_names: set[str] = set()
        seen_events: set[str] = set()
        seen_contexts: set[str] = set()
        seen_relations: set[tuple[str, str, str]] = set()
        proposal_rows: list[list[Any]] = []
        paragraphs = list(filter(None, re.split(r"\n\s*\n", chapter.plain_text.strip())))
        for paragraph_number, paragraph in enumerate(paragraphs, start=1):
            segment_id = uuid4()
            self.client.insert(
                "source_segment",
                [[segment_id, graph_id, chapter.sequence, paragraph_number, paragraph, paragraph]],
                column_names=["id", "graph_id", "chapter", "sequence", "original_text", "normalized_text"],
            )
            for sentence in filter(None, re.split(r"(?<=[.!?])\s+", paragraph)):
                sentence = sentence.strip()
                if not sentence:
                    continue
                for match in re.finditer(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)*\b", sentence):
                    name = match.group(0)
                    normalized = name.casefold()
                    if normalized in seen_names or normalized in existing_names or name in {"The", "And", "But", "For", "With", "This", "That", "When", "After", "Before"}:
                        continue
                    seen_names.add(normalized)
                    entity_id, evidence_id, proposal_id = uuid4(), uuid4(), uuid4()
                    known_entity_ids[normalized] = str(entity_id)
                    entity_type = "location" if re.search(r"\b(?:City|Town|Forest|Castle|River|Sea|Mountain)\b", name) else "character"
                    payload = {"operations": [
                        {"id": str(entity_id), "operation_type": "create_entity", "payload": {"id": str(entity_id), "name": name, "type": entity_type, "status": "active", "description": f"Mentioned in chapter {chapter.sequence}: {sentence}", "confidence": 0.7, "aliases": [], "metadata": {"chapter_id": str(chapter.id)}}},
                        {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(entity_id), "node_type": "entity"}},
                        {"id": str(evidence_id), "operation_type": "create_evidence", "payload": {"id": str(evidence_id), "source_segment_id": str(segment_id), "excerpt": name, "start_offset": paragraph.find(name), "end_offset": paragraph.find(name) + len(name), "confidence": 0.7}},
                        {"id": str(uuid4()), "operation_type": "link_evidence", "payload": {"evidence_id": str(evidence_id), "target_type": "ENTITY", "target_id": str(entity_id)}},
                    ]}
                    proposal_rows.append([proposal_id, run_id, graph_id, chapter.id, "create_entity", json.dumps(payload), json.dumps({"summary": f"Add {name} as a {entity_type}", "excerpt": sentence, "chapter_id": str(chapter.id), "segment_id": str(segment_id)}), "proposed"])

                mentioned_entities = []
                for match in re.finditer(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)*\b", sentence):
                    name = match.group(0)
                    entity_id = known_entity_ids.get(name.casefold())
                    if entity_id and all(entity_id != item[1] for item in mentioned_entities):
                        mentioned_entities.append((name, entity_id))
                if len(mentioned_entities) >= 2:
                    source, target = mentioned_entities[:2]
                    predicate_match = re.search(r"\b(meets?|met|attacks?|attacked|helps?|helped|trusts?|trusted|opposes?|opposed|follows?|followed|finds?|found|gives?|gave|takes?|took|asks?|asked|tells?|told|kills?|killed)\b", sentence, re.IGNORECASE)
                    predicate = predicate_match.group(0).casefold() if predicate_match else "related_to"
                    relation_key = (source[1], predicate, target[1])
                    if relation_key not in seen_relations:
                        seen_relations.add(relation_key)
                        relation_id, proposal_id = uuid4(), uuid4()
                        payload = {"operations": [
                            {"id": str(relation_id), "operation_type": "create_relation", "payload": {"id": str(relation_id), "source_node_id": source[1], "target_node_id": target[1], "relation_type": "statement", "label": predicate, "description": sentence, "status": "draft", "confidence": 0.6, "metadata": {"chapter_id": str(chapter.id)}}},
                            {"id": str(uuid4()), "operation_type": "create_knowledge_element", "payload": {"id": str(relation_id), "element_type": "statement", "description": sentence, "origin": "agent", "status": "draft", "confidence": 0.6, "metadata": {"chapter_id": str(chapter.id)}}},
                            {"id": str(uuid4()), "operation_type": "create_statement", "payload": {"id": str(relation_id), "subject_entity_id": source[1], "predicate": predicate, "object_entity_id": target[1], "description": sentence, "status": "draft", "confidence": 0.6, "metadata": {"chapter_id": str(chapter.id)}}},
                            {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(relation_id), "node_type": "relation"}},
                            {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(relation_id), "node_type": "knowledge_element"}},
                        ]}
                        proposal_rows.append([proposal_id, run_id, graph_id, chapter.id, "create_relation", json.dumps(payload), json.dumps({"summary": f"Add relation: {source[0]} {predicate.replace('_', ' ')} {target[0]}", "excerpt": sentence, "chapter_id": str(chapter.id), "segment_id": str(segment_id)}), "proposed"])

                event_match = re.search(r"\b(arrives?|arrived|leaves?|left|meets?|met|finds?|found|discovers?|discovered|attacks?|attacked|escapes?|escaped|reveals?|revealed|decides?|decided|enters?|entered|walks?|walked|runs?|ran|speaks?|spoke|says?|said|asks?|asked|takes?|took|gives?|gave|opens?|opened|closes?|closed|kills?|killed|helps?|helped|hides?|hid|waits?|waited)\b", sentence, re.IGNORECASE)
                if event_match:
                    event_name = sentence[:160].rstrip(".!? ")
                    normalized_event = event_name.casefold()
                    if normalized_event not in seen_events:
                        seen_events.add(normalized_event)
                        event_id, proposal_id = uuid4(), uuid4()
                        payload = {"operations": [
                            {"id": str(event_id), "operation_type": "create_event", "payload": {"id": str(event_id), "name": event_name, "type": "story_event", "status": "draft", "description": sentence, "confidence": 0.65, "metadata": {"chapter_id": str(chapter.id)}}},
                            {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(event_id), "node_type": "event"}},
                        ]}
                        proposal_rows.append([proposal_id, run_id, graph_id, chapter.id, "create_event", json.dumps(payload), json.dumps({"summary": f"Add event: {event_name}", "excerpt": sentence, "chapter_id": str(chapter.id), "segment_id": str(segment_id)}), "proposed"])

                context_match = re.search(r"\b(?:in|at|inside|within|near)\s+(?:the\s+)?([A-Za-z][A-Za-z' -]{2,40})", sentence)
                if context_match:
                    setting = context_match.group(1)
                    normalized_setting = setting.casefold()
                    if normalized_setting not in seen_contexts:
                        seen_contexts.add(normalized_setting)
                        context_id, proposal_id = uuid4(), uuid4()
                        payload = {"operations": [
                            {"id": str(context_id), "operation_type": "create_context", "payload": {"id": str(context_id), "type": "setting", "description": f"Scene setting: {setting}", "holder_entity_id": None, "confidence": 0.65, "metadata": {"chapter_id": str(chapter.id)}}},
                            {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(context_id), "node_type": "context"}},
                        ]}
                        proposal_rows.append([proposal_id, run_id, graph_id, chapter.id, "create_context", json.dumps(payload), json.dumps({"summary": f"Add setting: {setting}", "excerpt": sentence, "chapter_id": str(chapter.id), "segment_id": str(segment_id)}), "proposed"])

                if re.search(r"\b(?:believes?|thinks?|suspects?|seems?|appears?|may|might|perhaps|rumou?red)\b", sentence, re.IGNORECASE):
                    element_id, proposal_id = uuid4(), uuid4()
                    payload = {"operations": [
                        {"id": str(element_id), "operation_type": "create_knowledge_element", "payload": {"id": str(element_id), "element_type": "assumption", "description": sentence, "origin": "agent", "status": "draft", "confidence": 0.55, "metadata": {"chapter_id": str(chapter.id)}}},
                        {"id": str(uuid4()), "operation_type": "link_node_to_chapter", "payload": {"chapter_id": str(chapter.id), "node_id": str(element_id), "node_type": "knowledge_element"}},
                    ]}
                    proposal_rows.append([proposal_id, run_id, graph_id, chapter.id, "create_knowledge_element", json.dumps(payload), json.dumps({"summary": "Add narrative assumption", "excerpt": sentence, "chapter_id": str(chapter.id), "segment_id": str(segment_id)}), "proposed"])
        if proposal_rows:
            self.client.insert(
                "chapter_analysis_proposal", proposal_rows,
                column_names=["id", "run_id", "graph_id", "chapter_id", "operation_type", "payload", "provenance", "status"],
            )

    def suggest_text(self, graph_id: UUID, chapter_id: UUID) -> list[dict[str, str]]:
        """Suggest prose additions for graph facts absent from the current chapter text."""
        chapter = self.get_chapter(graph_id, chapter_id)
        draft = chapter.plain_text.casefold()
        memberships = result_rows(self.client.query(
            "SELECT node_id, node_type FROM chapter_node WHERE graph_id = {graph_id:UUID} AND chapter_id = {chapter_id:UUID}",
            parameters={"graph_id": graph_id, "chapter_id": chapter_id},
        ))
        ids_by_type: dict[str, set[str]] = {"entity": set(), "event": set(), "context": set(), "knowledge_element": set(), "relation": set()}
        for membership in memberships:
            if membership["node_type"] in ids_by_type:
                ids_by_type[membership["node_type"]].add(str(membership["node_id"]))
        entities = result_rows(self.client.query(
            "SELECT id, name, description FROM entity WHERE graph_id = {graph_id:UUID} AND status != 'deleted'",
            parameters={"graph_id": graph_id},
        ))
        events = result_rows(self.client.query(
            "SELECT id, name, description FROM event WHERE graph_id = {graph_id:UUID} AND status != 'deleted'",
            parameters={"graph_id": graph_id},
        ))
        contexts = result_rows(self.client.query(
            "SELECT id, type, description FROM context WHERE graph_id = {graph_id:UUID}",
            parameters={"graph_id": graph_id},
        ))
        knowledge = result_rows(self.client.query(
            "SELECT id, element_type, description FROM knowledge_element "
            "WHERE graph_id = {graph_id:UUID} AND status != 'invalidated'",
            parameters={"graph_id": graph_id},
        ))
        labels = {
            **{str(item["id"]): str(item["name"]) for item in entities},
            **{str(item["id"]): str(item["name"]) for item in events},
            **{str(item["id"]): str(item["description"] or item["type"]) for item in contexts},
        }
        suggestions: list[dict[str, str]] = []
        chapter_contexts = [
            item for item in contexts
            if str(item["id"]) in ids_by_type["context"] and str(item["description"] or "").strip()
        ]
        setting_opening = ""
        if chapter_contexts:
            setting = str(chapter_contexts[0]["description"]).replace("Scene setting:", "").strip()
            setting_opening = f"In {setting}," if setting else ""
        relations = result_rows(self.client.query(
            "SELECT id, source_node_id, target_node_id, relation_type, label, description FROM graph_relation "
            "WHERE graph_id = {graph_id:UUID} AND status != 'deleted'",
            parameters={"graph_id": graph_id},
        ))
        for relation in relations:
            if str(relation["id"]) not in ids_by_type["relation"]:
                continue
            source = labels.get(str(relation["source_node_id"]))
            target = labels.get(str(relation["target_node_id"]))
            label = str(relation["label"])
            if not source or not target or (source.casefold() in draft and target.casefold() in draft and label.casefold() in draft):
                continue
            predicate = label.replace("_", " ")
            passage = f"{setting_opening} {source} {predicate} {target}.".strip()
            description = str(relation["description"] or "").strip()
            if description and description.casefold() not in draft and not description.startswith("Mentioned in chapter"):
                passage = f"{passage} {description.rstrip('.!?')}."
            suggestions.append({"id": str(relation["id"]), "text": passage, "rationale": f"Adds a story beat for the graph relation: {source} {predicate} {target}."})
        for item in events:
            item_id = str(item["id"])
            belongs_to_chapter = item_id in ids_by_type["event"]
            label = labels[item_id]
            description = str(item["description"] or "").strip()
            if not belongs_to_chapter or not description or label.casefold() in draft:
                continue
            text = description if description.endswith((".", "!", "?")) else f"{description}."
            if setting_opening and not text.casefold().startswith(setting_opening.casefold()):
                text = f"{setting_opening} {text[0].lower()}{text[1:]}"
            suggestions.append({"id": item_id, "text": text, "rationale": f"Adds the planned event “{label}” as a complete story beat."})
        for item in knowledge:
            if str(item["id"]) not in ids_by_type["knowledge_element"] or item["element_type"] not in {"assumption", "fact", "constraint"}:
                continue
            description = str(item["description"] or "").strip()
            if not description or description.casefold() in draft:
                continue
            text = description if description.endswith((".", "!", "?")) else f"{description}."
            if item["element_type"] == "assumption":
                text = f"{text} For now, no one can be certain what it means."
            suggestions.append({"id": str(item["id"]), "text": text, "rationale": f"Weaves the chapter’s {item['element_type']} into the prose."})
        return suggestions[:6]

    def get_proposals(self, graph_id: UUID, chapter_id: UUID, run_id: UUID) -> list[dict[str, Any]]:
        result = self.client.query(
            "SELECT id, operation_type, payload, provenance, status FROM chapter_analysis_proposal FINAL "
            "WHERE run_id = {run_id:UUID} AND graph_id = {graph_id:UUID} AND chapter_id = {chapter_id:UUID} ORDER BY id",
            parameters={"run_id": run_id, "graph_id": graph_id, "chapter_id": chapter_id},
        )
        proposals = result_rows(result)
        for proposal in proposals:
            if isinstance(proposal["payload"], str):
                proposal["payload"] = json.loads(proposal["payload"])
            if isinstance(proposal["provenance"], str):
                proposal["provenance"] = json.loads(proposal["provenance"])
        return proposals

    def mark_proposals(self, graph_id: UUID, chapter_id: UUID, run_id: UUID, proposal_ids: list[UUID], status: str) -> list[dict[str, Any]]:
        proposals = self.get_proposals(graph_id, chapter_id, run_id)
        selected = {str(item) for item in proposal_ids}
        for proposal in proposals:
            if str(proposal["id"]) not in selected:
                continue
            self.client.insert(
                "chapter_analysis_proposal",
                [[proposal["id"], run_id, graph_id, chapter_id, proposal["operation_type"], json.dumps(proposal["payload"]), json.dumps(proposal["provenance"]), status]],
                column_names=["id", "run_id", "graph_id", "chapter_id", "operation_type", "payload", "provenance", "status"],
            )
        return self.get_proposals(graph_id, chapter_id, run_id)
