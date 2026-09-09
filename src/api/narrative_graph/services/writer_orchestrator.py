"""Real ADK stage execution for durable writer runs."""
from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from typing import Any, Awaitable, Callable

from src.config import settings

StageExecutor = Callable[[dict[str, Any], Any], Awaitable[dict[str, Any]]]
StageUpdate = Callable[..., None]
StageState = Callable[..., list[dict[str, Any]]]
Cancelled = Callable[[], bool]


class WriterOrchestrator:
    STAGES: dict[str, list[tuple[str, str]]] = {
        "analysis": [("ingestion", "Segmenting chapter text"), ("narrative_analysis", "Analyzing narrative structure"), ("entity_resolution", "Resolving entities"), ("event_extraction", "Extracting events and relations"), ("statement_extraction", "Extracting statements"), ("time_context_resolution", "Resolving time and context"), ("graph_integration", "Preparing reviewable graph proposals"), ("validation", "Validating proposed graph changes")],
        "draft": [("story_request_interpreter", "Interpreting drafting request"), ("graph_retrieval", "Retrieving canonical story context"), ("narrative_planner", "Planning narrative beats"), ("scene_planner", "Planning scenes"), ("prose_writer", "Writing draft prose"), ("style", "Refining style and continuity")],
        "review": [("narrative_consistency", "Checking continuity"), ("graph_feedback", "Preparing graph feedback")],
        "research": [("historical_investigator", "Researching historical accuracy and lore")],
        "visuals": [("scene_detection", "Detecting visual scenes"), ("scenographer", "Generating storyboard concepts")],
        "voice": [("dialogue_extraction", "Separating narration and dialogue"), ("dialogue_tts", "Generating voiced audio")],
        "produce": [("story_planning", "Planning production"), ("chapter_production", "Producing authored chapters"), ("artifact_assembly", "Assembling story artifacts")],
    }

    @staticmethod
    def _agent(name: str) -> Any | None:
        # Lazy imports keep ordinary API and media-only startup independent of ADK.
        text_stages = {
            "ingestion", "narrative_analysis", "entity_resolution", "event_extraction",
            "statement_extraction", "time_context_resolution", "graph_integration", "validation",
        }
        if name in text_stages:
            from src.agent import text_to_graph
            mapping = {
            "ingestion": text_to_graph.ingestion_agent, "narrative_analysis": text_to_graph.narrative_analyzer,
            "entity_resolution": text_to_graph.entity_resolution_agent, "event_extraction": text_to_graph.event_extraction_agent,
            "statement_extraction": text_to_graph.statement_extraction_agent, "time_context_resolution": text_to_graph.time_resolution_agent,
            "graph_integration": text_to_graph.graph_integration_agent, "validation": text_to_graph.validation_agent,
            }
            return mapping[name]
        if name not in {"story_request_interpreter", "graph_retrieval", "narrative_planner", "scene_planner", "prose_writer", "style", "narrative_consistency", "graph_feedback"}:
            return None
        from src.agent import graph_to_text
        mapping = {
            "story_request_interpreter": graph_to_text.story_request_interpreter, "graph_retrieval": graph_to_text.graph_retrieval_agent,
            "narrative_planner": graph_to_text.narrative_planner, "scene_planner": graph_to_text.scene_planner,
            "prose_writer": graph_to_text.prose_writer, "style": graph_to_text.style_agent,
            "narrative_consistency": graph_to_text.narrative_consistency_agent, "graph_feedback": graph_to_text.graph_feedback_agent,
        }
        return mapping.get(name)

    @staticmethod
    def _fingerprint(context: dict[str, Any]) -> str:
        return sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()

    async def _run_adk(self, agent: Any, *, run_id: str, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("Gemini is not configured; configure GEMINI_API_KEY before starting AI writer runs")
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types
        app_name, user_id, session_id = "cinemagent_writer", f"writer-{run_id}", f"{run_id}-{stage}"
        sessions = InMemorySessionService()
        await sessions.create_session(app_name=app_name, user_id=user_id, session_id=session_id, state={"writer_context": context})
        runner = Runner(app_name=app_name, agent=agent, session_service=sessions)
        prompt = json.dumps({"task": "Return a concise JSON object. Do not apply mutations.", "stage": stage, "context": context}, default=str)
        parts: list[str] = []
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
            for part in getattr(getattr(event, "content", None), "parts", []) or []:
                if getattr(part, "text", None):
                    parts.append(part.text)
        text = "\n".join(parts).strip()
        try:
            parsed: Any = json.loads(text.removeprefix("```json").removesuffix("```").strip())
        except json.JSONDecodeError:
            parsed = {"summary": text[:8_000]}
        if not isinstance(parsed, dict):
            raise ValueError(f"ADK stage {stage} returned no structured object")
        return {"provider": "google-adk", "agent": getattr(agent, "name", stage), "output": parsed}

    async def run(self, row: dict[str, Any], chapter: Any, execute: StageExecutor, update: StageUpdate,
                  stage_state: StageState, cancelled: Cancelled) -> dict[str, Any]:
        stages, attempt = self.STAGES[row["agent_group"]], int(row.get("attempt", 1))
        context = {"graph_id": str(row["graph_id"]), "chapter_id": str(row.get("chapter_id") or ""), "instruction": row.get("input", {}).get("instruction", ""), "options": row.get("input", {}).get("options", {}), "chapter": None if not chapter else {"title": chapter.title, "text": chapter.plain_text, "revision": chapter.revision}}
        fingerprint = self._fingerprint(context)
        completed = {item["name"] for item in stage_state(row["id"], attempt) if item["status"] == "completed" and item.get("input_fingerprint") == fingerprint}
        diagnostics: dict[str, Any] = {}
        for index, (name, message) in enumerate(stages, start=1):
            if cancelled():
                raise asyncio.CancelledError("Writer cancelled this run")
            progress = min(95, max(5, int(index * 90 / len(stages))))
            if name in completed:
                continue
            update(row, stage=name, stage_status="running", progress=progress, message=message, fingerprint=fingerprint)
            try:
                agent = self._agent(name)
                diagnostics[name] = await self._run_adk(agent, run_id=str(row["id"]), stage=name, context=context) if agent else {"provider": "specialized-executor", "agent": name}
            except Exception as error:
                update(row, stage=name, stage_status="failed", progress=progress, message=f"{message} failed", fingerprint=fingerprint, error=str(error))
                raise
            if cancelled():
                raise asyncio.CancelledError("Writer cancelled this run")
            update(row, stage=name, stage_status="completed", progress=progress, message=message, fingerprint=fingerprint, output=diagnostics[name])
        result = await execute(row, chapter)
        return {**result, "orchestrator": "google-adk-writer", "adk_stages": diagnostics, "source_revision": context["chapter"]["revision"] if context["chapter"] else None}
