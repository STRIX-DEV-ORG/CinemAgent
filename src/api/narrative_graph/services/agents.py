"""Durable, writer-facing adapters for the existing CinemAgent agents."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException

from src.agent.dialogue_tts_agent import dialogue_tts_executor
from src.agent.models import DialogerRequest, InvestigatorRequest, ScenographerRequest
from src.agent.scenographer_agent import scenographer_executor
from src.agent.searcher_agent import searcher_investigator_executor
from src.agent.tools.pdf_generator import ScreenplayPDFGenerator

from ..models import AgentRunCreate, AgentRunResponse, AgentRunReview, AgentRunStage, ChapterDocumentUpdate
from .common import result_rows
from .writer_orchestrator import WriterOrchestrator


class AgentRunService:
    """Coordinates agent output with chapter drafts and the graph workspace.

    The ADK pipelines are intentionally represented as groups: a writer asks
    for an analysis or draft, while the returned result keeps each stage's
    output available to the UI for transparent review.
    """

    def __init__(self, client: Any, workspace: Any, graphs: Any) -> None:
        self.client = client
        self.workspace = workspace
        self.graphs = graphs
        self.intelligence: Any | None = None
        self.orchestrator = WriterOrchestrator()

    def _chapter_voice_cast(self, graph_id: UUID, chapter_id: UUID) -> tuple[dict[str, str], dict[str, str]]:
        """Return stable voice presets and entity IDs for chapter characters."""
        memberships = result_rows(self.client.query(
            "SELECT node_id FROM chapter_node WHERE graph_id = {graph_id:UUID} "
            "AND chapter_id = {chapter_id:UUID} AND node_type = 'entity'",
            parameters={"graph_id": graph_id, "chapter_id": chapter_id},
        ))
        member_ids = {str(row["node_id"]) for row in memberships}
        if not member_ids:
            return {}, {}
        entities = result_rows(self.client.query(
            "SELECT id, name FROM entity WHERE graph_id = {graph_id:UUID} "
            "AND status != 'deleted'",
            parameters={"graph_id": graph_id},
        ))
        voice_presets = ("Aoede", "Fenrir", "Puck", "Charon", "Kore")
        cast = [row for row in entities if str(row["id"]) in member_ids]
        cast.sort(key=lambda row: str(row["name"]).casefold())
        voice_hints = {
            str(row["name"]): voice_presets[index % len(voice_presets)]
            for index, row in enumerate(cast)
        }
        entity_ids = {str(row["name"]): str(row["id"]) for row in cast}
        return voice_hints, entity_ids

    def _chapter_visual_context(self, graph_id: UUID, chapter_id: UUID) -> dict[str, list[dict[str, str]]]:
        """Give the scenographer canonical visual facts, not just raw prose."""
        memberships = result_rows(self.client.query(
            "SELECT node_id, node_type FROM chapter_node WHERE graph_id = {graph_id:UUID} "
            "AND chapter_id = {chapter_id:UUID}",
            parameters={"graph_id": graph_id, "chapter_id": chapter_id},
        ))
        ids = {kind: {str(row["node_id"]) for row in memberships if row["node_type"] == kind}
               for kind in ("entity", "context", "knowledge_element")}
        unified_query = """
        SELECT 'entity' AS _node_type, id, name, type, description, content, aliases FROM entity WHERE graph_id = {graph_id:UUID} AND status != 'deleted'
        UNION ALL
        SELECT 'context' AS _node_type, id, name, type, description, content, '' AS aliases FROM context WHERE graph_id = {graph_id:UUID}
        UNION ALL
        SELECT 'knowledge_element' AS _node_type, id, name, element_type AS type, description, content, '' AS aliases FROM knowledge_element WHERE graph_id = {graph_id:UUID} AND status != 'invalidated'
        """
        all_nodes = result_rows(self.client.query(unified_query, parameters={"graph_id": graph_id}))
        
        entities = [{"id": row["id"], "name": row["name"], "type": row["type"], "description": row["description"], "content": row["content"], "aliases": row["aliases"]} for row in all_nodes if row["_node_type"] == "entity"]
        contexts = [{"id": row["id"], "name": row["name"], "type": row["type"], "description": row["description"], "content": row["content"]} for row in all_nodes if row["_node_type"] == "context"]
        details = [{"id": row["id"], "name": row["name"], "element_type": row["type"], "description": row["description"], "content": row["content"]} for row in all_nodes if row["_node_type"] == "knowledge_element"]
        def compact(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, str]:
            return {field: str(row.get(field) or "")[:500] for field in fields if row.get(field)}
        included_entities = [row for row in entities if str(row["id"]) in ids["entity"]]
        return {
            "characters": [compact(row, ("name", "type", "description", "content", "aliases")) for row in included_entities if row.get("type") not in {"object", "location"}],
            "objects": [compact(row, ("name", "type", "description", "content")) for row in included_entities if row.get("type") == "object"],
            "locations": [compact(row, ("name", "type", "description", "content")) for row in included_entities if row.get("type") == "location"],
            "settings": [compact(row, ("name", "type", "description", "content")) for row in contexts if str(row["id"]) in ids["context"]],
            "visual_facts": [compact(row, ("name", "element_type", "description", "content")) for row in details if str(row["id"]) in ids["knowledge_element"] and row.get("element_type") in {"attribute", "fact", "constraint"}],
        }

    def start(self, graph_id: UUID, request: AgentRunCreate) -> AgentRunResponse:
        self.graphs.get_graph(graph_id)
        if request.scope == "chapter" and request.chapter_id is None:
            raise HTTPException(status_code=422, detail="chapter_id is required for a chapter agent run")
        if request.chapter_id:
            self.workspace.get_chapter(graph_id, request.chapter_id)
        run_id = uuid4()
        source_revision = None
        if request.chapter_id:
            source_revision = self.workspace.get_chapter(graph_id, request.chapter_id).revision
        payload = {"instruction": request.instruction, "options": request.options, "source_revision": source_revision}
        self.client.insert(
            "agent_run",
            [[run_id, graph_id, request.chapter_id, request.agent_group, request.scope, json.dumps(payload, default=str), "queued", 0, "Queued", None, json.dumps({})]],
            column_names=["id", "graph_id", "chapter_id", "agent_group", "scope", "input", "status", "progress", "message", "error", "result"],
        )
        if self.intelligence:
            self.intelligence.append_event(graph_id, "agent_run_queued", actor_type="agent", chapter_id=request.chapter_id,
                                           operation_id=run_id, payload={"agent_group": request.agent_group, "scope": request.scope})
        return self.get(graph_id, run_id)

    def _row(self, graph_id: UUID, run_id: UUID) -> dict[str, Any]:
        rows = result_rows(self.client.query(
            "SELECT id, graph_id, chapter_id, agent_group, scope, input, status, progress, message, error, result "
            "FROM agent_run WHERE graph_id = {graph_id:UUID} AND id = {run_id:UUID} ORDER BY updated_at DESC LIMIT 1",
            parameters={"graph_id": graph_id, "run_id": run_id},
        ))
        if not rows:
            raise HTTPException(status_code=404, detail="agent run not found")
        row = rows[0]
        if isinstance(row.get("result"), str):
            row["result"] = json.loads(row["result"] or "{}")
        if isinstance(row.get("input"), str):
            row["input"] = json.loads(row["input"] or "{}")
        return row

    def get(self, graph_id: UUID, run_id: UUID) -> AgentRunResponse:
        row = self._row(graph_id, run_id)
        result = row.get("result", {})
        source_revision = row.get("input", {}).get("source_revision")
        stale = False
        if row.get("chapter_id") and source_revision is not None:
            stale = self.workspace.get_chapter(graph_id, row["chapter_id"]).revision != source_revision
        return AgentRunResponse(**row, attempt=int(result.get("retry_count", 0)) + 1,
                                source_revision=source_revision, stale=stale,
                                stages=[AgentRunStage(**stage) for stage in self._stage_states(row["id"], int(result.get("retry_count", 0)) + 1)])

    def cancel(self, graph_id: UUID, run_id: UUID) -> AgentRunResponse:
        row = self._row(graph_id, run_id)
        if row["status"] not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="only queued or running runs can be cancelled")
        self._update(row, status="cancelled", progress=row["progress"], message="Cancelled by writer")
        return self.get(graph_id, run_id)

    def retry(self, graph_id: UUID, run_id: UUID) -> AgentRunResponse:
        row = self._row(graph_id, run_id)
        if row["status"] != "failed":
            raise HTTPException(status_code=409, detail="only failed runs can be retried")
        result = dict(row.get("result", {}))
        result["retry_count"] = int(result.get("retry_count", 0)) + 1
        result["stage_runs"] = []
        self._update(row, status="queued", progress=0, message="Queued for retry", result=result, error=None)
        return self.get(graph_id, run_id)

    def save_storyboards(self, graph_id: UUID, run_id: UUID, selected_scene_ids: list[str]) -> AgentRunResponse:
        row = self._row(graph_id, run_id)
        if row["agent_group"] != "visuals":
            raise HTTPException(status_code=422, detail="storyboard decisions are only available for visual runs")
        if row["status"] not in {"completed", "reviewed"}:
            raise HTTPException(status_code=409, detail="wait for storyboard generation to finish")
        visual = row.get("result", {}).get("visual", {})
        scenes = visual.get("scenes", []) if isinstance(visual, dict) else []
        by_id = {str(scene.get("scene_id")): scene for scene in scenes if scene.get("scene_id")}
        requested = set(selected_scene_ids)
        unknown = requested - set(by_id)
        if unknown:
            raise HTTPException(status_code=422, detail="one or more selected storyboard scenes do not belong to this run")
        result = dict(row.get("result", {}))
        stored = set(result.get("stored_scene_ids", []))
        for scene_id in requested - stored:
            scene = by_id[scene_id]
            storage_url = scene.get("image_url") or scene.get("image_path") or ""
            if storage_url:
                self._save_artifact(row, "image", str(scene.get("title") or "Storyboard scene"), storage_url, "image/png", scene)
                stored.add(scene_id)
        result["stored_scene_ids"] = sorted(stored)
        self._update(
            row,
            status="reviewed",
            progress=100,
            message=f"Stored {len(stored)} storyboard image(s)",
            result=result,
        )
        return self.get(graph_id, run_id)

    def list(self, graph_id: UUID, chapter_id: UUID | None = None) -> list[AgentRunResponse]:
        clause = "AND chapter_id = {chapter_id:UUID}" if chapter_id else ""
        parameters: dict[str, Any] = {"graph_id": graph_id}
        if chapter_id:
            parameters["chapter_id"] = chapter_id
        rows = result_rows(self.client.query(
            "SELECT id, graph_id, chapter_id, agent_group, scope, input, status, progress, message, error, result "
            f"FROM agent_run WHERE graph_id = {{graph_id:UUID}} {clause} ORDER BY updated_at DESC LIMIT 100",
            parameters=parameters,
        ))
        for row in rows:
            if isinstance(row.get("result"), str):
                row["result"] = json.loads(row["result"] or "{}")
            if isinstance(row.get("input"), str):
                row["input"] = json.loads(row["input"] or "{}")
        return [self.get(graph_id, row["id"]) for row in rows]

    def _stage_states(self, run_id: UUID, attempt: int) -> list[dict[str, Any]]:
        rows = result_rows(self.client.query(
            "SELECT name, argMax(attempt, occurred_at) AS attempt, argMax(status, occurred_at) AS status, argMax(progress, occurred_at) AS progress, "
            "argMax(message, occurred_at) AS message, argMax(error, occurred_at) AS error, "
            "argMax(output, occurred_at) AS output, argMax(input_fingerprint, occurred_at) AS input_fingerprint "
            "FROM agent_run_stage WHERE run_id = {run_id:UUID} AND attempt <= {attempt:UInt32} GROUP BY name ORDER BY min(occurred_at)",
            parameters={"run_id": run_id, "attempt": attempt},
        ))
        for item in rows:
            if isinstance(item.get("output"), str):
                item["output"] = json.loads(item["output"] or "{}")
        return rows

    def _update_stage(self, row: dict[str, Any], *, stage: str, stage_status: str, progress: int,
                      message: str, fingerprint: str, output: dict[str, Any] | None = None,
                      error: str | None = None) -> None:
        attempt = int(row.get("attempt", 1))
        token = row.get("lease_token") or uuid4()
        self.client.insert("agent_run_stage", [[row["id"], row["graph_id"], row.get("chapter_id"), attempt, token,
            stage, stage_status, progress, message, fingerprint, json.dumps(output or {}, default=str), error]],
            column_names=["run_id", "graph_id", "chapter_id", "attempt", "lease_token", "name", "status", "progress", "message", "input_fingerprint", "output", "error"])
        self._update(row, status="running", progress=progress, message=message)

    def _is_cancelled(self, graph_id: UUID, run_id: UUID) -> bool:
        return self._row(graph_id, run_id)["status"] == "cancelled"

    def _claim(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Cooperative ClickHouse lease; effects remain idempotent if a race occurs."""
        token, worker_id = uuid4(), os.getenv("NARRATIVE_AGENT_WORKER_ID", f"worker-{os.getpid()}")
        attempt = int(row.get("result", {}).get("retry_count", 0)) + 1
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        self.client.insert("agent_run_lease", [[row["id"], row["graph_id"], attempt, worker_id, token, expires]],
                           column_names=["run_id", "graph_id", "attempt", "worker_id", "lease_token", "expires_at"])
        latest = result_rows(self.client.query(
            "SELECT lease_token, expires_at FROM agent_run_lease WHERE run_id = {run_id:UUID} AND attempt = {attempt:UInt32} "
            "ORDER BY claimed_at DESC LIMIT 1", parameters={"run_id": row["id"], "attempt": attempt}))
        if not latest or latest[0]["lease_token"] != token:
            return None
        row = dict(row)
        row["attempt"], row["lease_token"] = attempt, token
        return row

    def _update(self, row: dict[str, Any], *, status: str, progress: int, message: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.client.insert(
            "agent_run",
            [[row["id"], row["graph_id"], row.get("chapter_id"), row["agent_group"], row["scope"], json.dumps(row.get("input", {}), default=str), status, progress, message, error, json.dumps(result if result is not None else row.get("result", {}), default=str)]],
            column_names=["id", "graph_id", "chapter_id", "agent_group", "scope", "input", "status", "progress", "message", "error", "result"],
        )
        if self.intelligence:
            self.intelligence.append_event(row["graph_id"], "agent_run_updated", actor_type="agent", chapter_id=row.get("chapter_id"),
                                           operation_id=row["id"], version=progress, payload={"agent_group": row["agent_group"], "scope": row["scope"], "status": status, "progress": progress, "message": message, "error": error})

    async def execute(self, graph_id: UUID, run_id: UUID) -> None:
        row = self._row(graph_id, run_id)
        if row["status"] != "queued":
            return
        row = self._claim(row)
        if row is None:
            return
        self._update(row, status="running", progress=5, message="Preparing narrative context")
        try:
            chapter = self.workspace.get_chapter(graph_id, row["chapter_id"]) if row.get("chapter_id") else None
            result = await self.orchestrator.run(row, chapter, self._execute_group, self._update_stage,
                                                 self._stage_states, lambda: self._is_cancelled(graph_id, run_id))
            if self._is_cancelled(graph_id, run_id):
                return
            result["retry_count"] = int(row.get("result", {}).get("retry_count", 0))
            self._update(row, status="completed", progress=100, message="Ready for review", result=result)
        except asyncio.CancelledError:
            self._update(row, status="cancelled", progress=row.get("progress", 0), message="Cancelled by writer")
        except Exception as error:  # Keep failures visible and retryable in the writer UI.
            self._update(row, status="failed", progress=100, message="Agent run failed", error=str(error))

    async def execute_queued(self, limit: int = 10) -> int:
        """Worker entry point; each completed row is safe to observe/retry."""
        rows = result_rows(self.client.query(
            "SELECT id, graph_id FROM agent_run WHERE status = 'queued' ORDER BY created_at LIMIT {limit:UInt32}",
            parameters={"limit": limit},
        ))
        for item in rows:
            await self.execute(item["graph_id"], item["id"])
        return len(rows)

    async def _execute_group(self, row: dict[str, Any], chapter: Any) -> dict[str, Any]:
        group = row["agent_group"]
        if group == "analysis":
            if not chapter:
                raise ValueError("analysis requires a chapter")
            analysis = self.workspace.start_analysis(row["graph_id"], chapter.id)
            proposals = self.workspace.get_proposals(row["graph_id"], chapter.id, analysis.id)
            return {"stages": ["ingestion", "narrative_analysis", "entity_resolution", "event_extraction", "statement_extraction", "time_resolution", "context_resolution", "graph_integration", "validation"], "analysis_run_id": str(analysis.id), "graph_proposals": proposals}
        if group == "draft":
            if not chapter:
                raise ValueError("draft requires a chapter")
            proposals = self.workspace.suggest_text(row["graph_id"], chapter.id)
            return {"stages": ["story_request_interpreter", "graph_retrieval", "narrative_planner", "scene_planner", "prose_writer", "style"], "text_patches": proposals}
        if group == "review":
            if not chapter:
                raise ValueError("review requires a chapter")
            suggestions = self.workspace.suggest_text(row["graph_id"], chapter.id)
            analysis = self.workspace.start_analysis(row["graph_id"], chapter.id)
            graph_proposals = self.workspace.get_proposals(row["graph_id"], chapter.id, analysis.id)
            findings = [
                {"severity": "warning", "message": item["rationale"], "suggestion": item["text"]}
                for item in suggestions
            ]
            if not findings:
                findings.append({
                    "severity": "success",
                    "message": "No uncovered chapter graph beats were found in the current draft.",
                    "suggestion": "The chapter text currently reflects its linked graph facts."
                })
            if graph_proposals:
                findings.append({
                    "severity": "info",
                    "message": f"Graph feedback found {len(graph_proposals)} fact(s) in the chapter that can be added or updated in the graph.",
                    "suggestion": "Review the extracted graph proposals and apply only the facts you want to preserve."
                })
            return {"stages": ["narrative_consistency", "graph_feedback"], "analysis_run_id": str(analysis.id), "findings": findings, "text_patches": suggestions, "graph_proposals": graph_proposals}
        if group == "research":
            if not chapter:
                raise ValueError("research requires a chapter")
            response = await searcher_investigator_executor.execute(InvestigatorRequest(query=row.get("input", {}).get("instruction") or chapter.plain_text, era_context=None, genre="historical fiction"))
            report = response.model_dump(mode="json")
            report["research_scope"] = {
                "chapter_title": chapter.title,
                "material": "The current chapter text",
                "checks": ["historical era and technology", "places, customs, and social details", "internal lore consistency"],
                "source_coverage": "external sources" if report.get("search_sources") else "local narrative audit only",
            }
            return {"stages": ["historical_investigator"], "report": report}
        if group == "visuals":
            if not chapter:
                raise ValueError("visuals requires a chapter")
            response = await scenographer_executor.execute(ScenographerRequest(chapter_text=chapter.plain_text, chapter_title=chapter.title, storyboard_context=self._chapter_visual_context(row["graph_id"], chapter.id)))
            return {"stages": ["scenographer", "scene_detection"], "artifact_ids": [], "visual": response.model_dump(mode="json"), "stored_scene_ids": []}
        if group == "voice":
            if not chapter:
                raise ValueError("voice requires a chapter")
            voice_hints, character_entity_ids = self._chapter_voice_cast(row["graph_id"], chapter.id)
            response = await dialogue_tts_executor.execute(DialogerRequest(
                chapter_text=chapter.plain_text,
                chapter_title=chapter.title,
                character_hints=voice_hints,
                character_entity_ids=character_entity_ids,
            ))
            artifact_ids = [str(self._save_artifact(row, "audio", line.speaker, line.audio_url or line.audio_path or "", "audio/mpeg" if str(line.audio_path or line.audio_url).endswith(".mp3") else "audio/wav", line.model_dump(mode="json"))) for line in response.dialogues if line.audio_url or line.audio_path]
            return {"stages": ["dialogue_tts"], "artifact_ids": artifact_ids, "dialogues": response.model_dump(mode="json")}
        options = row.get("input", {}).get("options", {})
        if chapter:
            return await self._produce_chapter(row, chapter, options)
        return await self._produce_story(row, options)

    async def _produce_story(self, row: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
        """Produce a story from its authored chapters, never the demo pipeline.

        The generic orchestrator contains development fallbacks that can emit
        a stock observatory screenplay. A story-level production run must use
        the writer's saved chapters as its scene source, just as chapter
        production uses the current chapter text.
        """
        chapters = [chapter for chapter in self.workspace.list_chapters(row["graph_id"])
                    if chapter.plain_text.strip()]
        if not chapters:
            raise ValueError("write text in at least one chapter before running story production")

        story = self.graphs.get_graph(row["graph_id"])
        artifact_ids: list[str] = []
        media_artifacts: list[dict[str, Any]] = []
        scenes_generation: dict[str, Any] = {}
        scene_plans: list[dict[str, Any]] = []

        for index, chapter in enumerate(chapters, start=1):
            chapter_text = chapter.plain_text.strip()
            scene_id = f"chapter_{chapter.id.hex[:8]}"
            scene_plans.append({
                "id": scene_id,
                "title": chapter.title,
                "purpose": f"Chapter {chapter.sequence}: {chapter.title}",
                "settingId": f"chapter_{chapter.sequence}",
            })
            chapter_media: dict[str, Any] = {
                "scene_id": scene_id,
                "chapter_id": str(chapter.id),
                "chapter_title": chapter.title,
                "dialogues": [],
            }
            if bool(options.get("enable_images", True)):
                visual = await scenographer_executor.execute(
                    ScenographerRequest(
                        chapter_text=chapter_text,
                        chapter_title=chapter.title,
                        storyboard_context=self._chapter_visual_context(row["graph_id"], chapter.id),
                    )
                )
                chapter_media.update({
                    "image_path": visual.image_path,
                    "image_url": visual.image_url,
                    "storyboards": [scene.model_dump(mode="json") for scene in visual.scenes],
                })
                for scene in visual.scenes:
                    storage_url = scene.image_url or scene.image_path or ""
                    if storage_url:
                        artifact_ids.append(str(self._save_artifact(
                            row, "image", f"{chapter.title}: {scene.title}", storage_url,
                            "image/png", scene.model_dump(mode="json"),
                        )))
            if bool(options.get("enable_tts", True)):
                voice_hints, character_entity_ids = self._chapter_voice_cast(row["graph_id"], chapter.id)
                dialogue = await dialogue_tts_executor.execute(DialogerRequest(
                    chapter_text=chapter_text,
                    chapter_title=chapter.title,
                    character_hints=voice_hints,
                    character_entity_ids=character_entity_ids,
                ))
                chapter_media["dialogues"] = [line.model_dump(mode="json") for line in dialogue.dialogues]
                for line in dialogue.dialogues:
                    storage_url = line.audio_url or line.audio_path or ""
                    if storage_url:
                        artifact_ids.append(str(self._save_artifact(
                            row, "audio", f"{chapter.title}: {line.speaker}", storage_url,
                            "audio/mpeg" if storage_url.endswith(".mp3") else "audio/wav",
                            line.model_dump(mode="json"),
                        )))
            media_artifacts.append(chapter_media)
            scenes_generation[scene_id] = {
                "sceneId": scene_id,
                "scenePlan": scene_plans[-1],
                "results": {
                    "prose_writer": {"prose": chapter_text},
                    "style_agent": {"polishedProse": chapter_text},
                },
            }

        story_text = "\n\n".join(f"{chapter.title}\n\n{chapter.plain_text.strip()}" for chapter in chapters)
        pdf_path = None
        if bool(options.get("enable_pdf", True)):
            pdf_path = ScreenplayPDFGenerator().generate_screenplay_pdf(
                task_id=f"story_{row['id'].hex[:12]}",
                title=story.name,
                story_request={"genre": "writer-authored story", "tone": "writer-authored"},
                narrative_outline={"title": story.name, "chapters": [chapter.title for chapter in chapters]},
                scene_plans_data={"scenePlans": scene_plans},
                scenes_generation=scenes_generation,
                media_artifacts=media_artifacts,
            )
            artifact_ids.append(str(self._save_artifact(
                row, "pdf", f"{story.name} screenplay", pdf_path, "application/pdf",
                {"chapter_count": len(chapters), "chapter_ids": [str(chapter.id) for chapter in chapters]},
            )))
        return {
            "stages": ["story_production", "chapter_assembly", "scenographer", "dialogue_tts", "pdf_screenplay_compiler"],
            "story_title": story.name,
            "story_text": story_text,
            "chapters": [{"id": str(chapter.id), "title": chapter.title, "sequence": chapter.sequence} for chapter in chapters],
            "artifact_ids": artifact_ids,
            "media": media_artifacts,
            "pdf_path": pdf_path,
        }

    async def _produce_chapter(self, row: dict[str, Any], chapter: Any, options: dict[str, Any]) -> dict[str, Any]:
        """Build production assets from the saved chapter, never fallback prose.

        The general orchestrator creates a new screenplay from a prompt.  A
        chapter production run instead preserves the writer's chapter exactly
        and only adds its storyboard, voice, and screenplay export wrappers.
        """
        chapter_text = chapter.plain_text.strip()
        if not chapter_text:
            raise ValueError("write chapter text before running production")
        scene_id = f"chapter_{chapter.id.hex[:8]}"
        media: dict[str, Any] = {"scene_id": scene_id, "dialogues": []}
        artifact_ids: list[str] = []
        if bool(options.get("enable_images", True)):
            visual = await scenographer_executor.execute(
                ScenographerRequest(chapter_text=chapter_text, chapter_title=chapter.title, storyboard_context=self._chapter_visual_context(row["graph_id"], chapter.id))
            )
            storyboards = [scene.model_dump(mode="json") for scene in visual.scenes]
            media.update({
                "image_path": visual.image_path,
                "image_url": visual.image_url,
                "storyboards": storyboards,
            })
            artifact_ids.extend(
                str(self._save_artifact(
                    row,
                    "image",
                    scene.title,
                    scene.image_url or scene.image_path or "",
                    "image/png",
                    scene.model_dump(mode="json"),
                ))
                for scene in visual.scenes
                if scene.image_url or scene.image_path
            )
        if bool(options.get("enable_tts", True)):
            voice_hints, character_entity_ids = self._chapter_voice_cast(row["graph_id"], chapter.id)
            dialogue = await dialogue_tts_executor.execute(
                DialogerRequest(
                    chapter_text=chapter_text,
                    chapter_title=chapter.title,
                    character_hints=voice_hints,
                    character_entity_ids=character_entity_ids,
                )
            )
            media["dialogues"] = [line.model_dump(mode="json") for line in dialogue.dialogues]
            for line in dialogue.dialogues:
                if line.audio_url or line.audio_path:
                    artifact_ids.append(str(self._save_artifact(row, "audio", line.speaker, line.audio_url or line.audio_path or "", "audio/mpeg" if str(line.audio_path or line.audio_url).endswith(".mp3") else "audio/wav", line.model_dump(mode="json"))))
        pdf_path = None
        if bool(options.get("enable_pdf", True)):
            pdf_path = ScreenplayPDFGenerator().generate_screenplay_pdf(
                task_id=f"chapter_{row['id'].hex[:12]}",
                title=chapter.title,
                story_request={"genre": "chapter draft", "tone": "writer-authored"},
                narrative_outline={"chapter": chapter.title},
                scene_plans_data={"scenePlans": [{"id": scene_id, "settingId": "chapter"}]},
                scenes_generation={scene_id: {"sceneId": scene_id, "results": {"prose_writer": {"prose": chapter_text}, "style_agent": {"polishedProse": chapter_text}}}},
                media_artifacts=[media],
            )
            artifact_ids.append(str(self._save_artifact(row, "pdf", f"{chapter.title} screenplay", pdf_path, "application/pdf", {"chapter_id": str(chapter.id)})))
        return {
            "stages": ["chapter_production", "scenographer", "dialogue_tts", "pdf_screenplay_compiler"],
            "chapter_id": str(chapter.id),
            "chapter_text": chapter_text,
            "artifact_ids": artifact_ids,
            "media": media,
            "pdf_path": pdf_path,
        }

    def _save_artifact(self, row: dict[str, Any], kind: str, title: str, storage_url: str, mime_type: str, metadata: dict[str, Any]) -> UUID:
        key = f"{row['id']}:{kind}:{title}:{storage_url}"
        existing = result_rows(self.client.query(
            "SELECT id FROM agent_artifact WHERE graph_id = {graph_id:UUID} AND run_id = {run_id:UUID} "
            "AND JSONExtractString(metadata, 'idempotency_key') = {key:String} LIMIT 1",
            parameters={"graph_id": row["graph_id"], "run_id": row["id"], "key": key},
        ))
        if existing:
            return existing[0]["id"]
        artifact_id = uuid5(NAMESPACE_URL, key)
        metadata = {**metadata, "idempotency_key": key}
        self.client.insert("agent_artifact", [[artifact_id, row["id"], row["graph_id"], row.get("chapter_id"), kind, title, storage_url, mime_type, json.dumps(metadata, default=str)]], column_names=["id", "run_id", "graph_id", "chapter_id", "kind", "title", "storage_url", "mime_type", "metadata"])
        return artifact_id

    def artifacts(self, graph_id: UUID, run_id: UUID) -> list[dict[str, Any]]:
        self._row(graph_id, run_id)
        rows = result_rows(self.client.query(
            "SELECT id, run_id, graph_id, chapter_id, kind, title, storage_url, mime_type, metadata "
            "FROM agent_artifact WHERE graph_id = {graph_id:UUID} AND run_id = {run_id:UUID} ORDER BY id",
            parameters={"graph_id": graph_id, "run_id": run_id},
        ))
        for item in rows:
            if isinstance(item.get("metadata"), str):
                item["metadata"] = json.loads(item["metadata"] or "{}")
        return rows

    def review(self, graph_id: UUID, run_id: UUID, request: AgentRunReview) -> AgentRunResponse:
        row = self._row(graph_id, run_id)
        source_revision = row.get("input", {}).get("source_revision")
        if row.get("chapter_id") and source_revision is not None:
            current = self.workspace.get_chapter(graph_id, row["chapter_id"])
            if current.revision != source_revision:
                raise HTTPException(status_code=409, detail="This output is stale because the chapter changed. Run the agent again before applying it.")
        result = row.get("result", {})
        accepted = set(request.accepted_text_ids)
        patches = [item for item in result.get("text_patches", []) if str(item.get("id")) in accepted]
        if patches and row.get("chapter_id"):
            chapter = self.workspace.get_chapter(graph_id, row["chapter_id"])
            document = dict(chapter.document)
            content = list(document.get("content", []))
            for patch in patches:
                content.append({"type": "paragraph", "content": [{"type": "text", "text": patch["text"]}]})
            document["content"] = content
            plain_text = "\n\n".join([chapter.plain_text, *[patch["text"] for patch in patches]]).strip()
            self.workspace.update_document(graph_id, chapter.id, ChapterDocumentUpdate(document=document, plain_text=plain_text, revision=chapter.revision))
        result["review"] = {"accepted_text_ids": list(accepted), "accepted_proposal_ids": [str(item) for item in request.accepted_proposal_ids]}
        self._update(row, status="reviewed", progress=100, message="Review saved", result=result)
        return self.get(graph_id, run_id)
