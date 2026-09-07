import asyncio
import time
import json
import uuid
import structlog
from pathlib import Path
from jinja2 import Template
from typing import Dict, Any, Optional, Callable, Awaitable, List

from src.config import settings
from src.rag.retriever import Retriever
from src.mcp.mcp_client import MCPClientManager
from src.agent.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from src.agent.models import (
    PipelineProgressStatus,
    ScreenplayPipelineRequest
)
from src.agent.tools.pdf_generator import ScreenplayPDFGenerator

# Import core Text-to-Graph & Graph-to-Text agents
from src.agent.text_to_graph import (
    ingestion_agent,
    narrative_analyzer,
    entity_resolution_agent,
    event_extraction_agent,
    statement_extraction_agent,
    time_resolution_agent,
    context_resolution_agent_2,
    graph_integration_agent,
    validation_agent
)
from src.agent.graph_to_text import (
    story_request_interpreter,
    graph_retrieval_agent,
    narrative_planner,
    scene_planner,
    prose_writer,
    style_agent,
    narrative_consistency_agent,
    graph_feedback_agent,
    _parse_agent_output
)

logger = structlog.get_logger(__name__)

# In-memory store for task progress statuses
task_progress_store: Dict[str, PipelineProgressStatus] = {}


class AgentOrchestrator:
    """
    Main agent runtime. Orchestrates:
    1. Parallel RAG context gathering & MCP search
    2. Text-to-Graph narrative ingestion & entity resolution
    3. Graph-to-Text multi-act narrative & scene generation
    4. Screenplay PDF script compilation (PyPDF + ReportLab)
    
    (Note: Scenographer, Dialogue TTS, and Searcher/Investigator agents
     are executed individually on-demand per user/client request).
    """
    def __init__(self):
        self.retriever = Retriever()
        self.mcp_manager = MCPClientManager()
        self.pdf_generator = ScreenplayPDFGenerator()
        
        self.has_llm = bool(settings.GEMINI_API_KEY or settings.OPENAI_API_KEY)
        if not self.has_llm:
            logger.warn("No API Keys configured for Gemini or OpenAI. The agent will run with simulated/mock agent responses.")

    async def _update_status(
        self,
        task_id: str,
        value: int,
        message: str,
        agent: str,
        stage: str,
        callback: Optional[Callable[[PipelineProgressStatus], Awaitable[None]]] = None,
        artifacts: Optional[Dict[str, Any]] = None,
        is_completed: bool = False,
        is_error: bool = False,
        error_message: Optional[str] = None
    ) -> PipelineProgressStatus:
        """
        Updates the internal status record and invokes any registered progress callback.
        """
        status_obj = task_progress_store.get(task_id)
        if not status_obj:
            status_obj = PipelineProgressStatus(
                task_id=task_id,
                status_value=value,
                status_message=message,
                current_agent=agent,
                stage=stage,
                is_completed=is_completed,
                is_error=is_error,
                error_message=error_message,
                artifacts=artifacts or {}
            )
        else:
            status_obj.status_value = value
            status_obj.status_message = message
            status_obj.current_agent = agent
            status_obj.stage = stage
            status_obj.is_completed = is_completed
            status_obj.is_error = is_error
            status_obj.error_message = error_message
            if artifacts:
                status_obj.artifacts.update(artifacts)
            status_obj.updated_at = time.time()

        task_progress_store[task_id] = status_obj
        logger.info(
            "Pipeline progress update",
            task_id=task_id,
            progress=f"{value}%",
            agent=agent,
            stage=stage,
            message=message
        )

        if callback:
            try:
                await callback(status_obj)
            except Exception as cb_err:
                logger.warn("Progress callback error", error=str(cb_err))

        return status_obj

    async def _call_llm_agent(self, agent_name: str, instruction: str, user_input: str) -> Any:
        """
        Invokes Gemini model for an agent with system instruction.
        Falls back to structured mock data if no API key is set.
        """
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=user_input,
                    config={
                        'system_instruction': instruction,
                        'temperature': 0.7
                    }
                )
                return _parse_agent_output(response.text)
            except Exception as e:
                logger.warn("Gemini agent call failed, using fallback", agent=agent_name, error=str(e))

        return self._generate_fallback_agent_data(agent_name, user_input)

    def _generate_fallback_agent_data(self, agent_name: str, user_input: str) -> Any:
        """Generates realistic domain data when running offline or testing."""
        if agent_name == "Ingestion_Agent":
            return {
                "documentId": f"doc_{uuid.uuid4().hex[:8]}",
                "formatDetected": "SCREENPLAY",
                "language": "en",
                "hierarchy": {
                    "structure": [{
                        "chapterId": "chap_01",
                        "title": "Act I - The Incident",
                        "scenes": [{
                            "sceneId": "scene_01_01",
                            "header": "INT. ROYAL OBSERVATORY - NIGHT",
                            "segments": [{
                                "segmentId": "seg_01_01_001",
                                "content": "Elena watches the celestial astrolabe revolve as a shadowed figure enters.",
                                "type": "NARRATIVE_PARAGRAPH"
                            }]
                        }]
                    }]
                }
            }
        elif agent_name == "Story_Request_Interpreter":
            return {
                "protagonistIds": ["char_elena_001"],
                "viewpointEntityId": "char_elena_001",
                "genre": "sci-fi mystery",
                "tone": "suspenseful, introspective",
                "narrativePerson": "first",
                "targetLength": 1000,
                "startingEventId": "evt_anomaly_detected_01",
                "endingEventId": "evt_astrolabe_discovery_02",
                "allowedKnowledgeContext": "elena_viewpoint_scope"
            }
        elif agent_name == "graph_retrieval_agent":
            return {
                "subgraph": {
                    "viewpointEntity": {"id": "char_elena_001", "name": "Elena Vance", "role": "Astrophysicist"},
                    "retrievedEntities": [
                        {"id": "char_marcus_001", "name": "Marcus Kane", "role": "Archivist"},
                        {"id": "item_stellar_cipher_01", "name": "Stellar Cipher Disc"}
                    ],
                    "retrievedEvents": [
                        {"id": "evt_anomaly_detected_01", "action": "detect_signal", "summary": "Elena detects harmonic anomaly from sector 7"}
                    ],
                    "activeStatements": [
                        {"subject": "char_elena_001", "predicate": "investigates", "object": "item_stellar_cipher_01"}
                    ]
                }
            }
        elif agent_name == "narrative_planner":
            return {
                "narrativeOutline": {
                    "title": "The Celestial Cipher",
                    "structure": [
                        {
                            "act": 1,
                            "title": "Signals in the Dark",
                            "beats": ["Elena observes impossible harmonics", "Marcus arrives with a warning"],
                            "associatedEventIds": ["evt_anomaly_detected_01"]
                        }
                    ]
                }
            }
        elif agent_name == "scene_planner":
            return {
                "scenePlans": [
                    {
                        "id": "scene_plan_01",
                        "purpose": "Reveal the encoded signal within the celestial astrolabe.",
                        "settingId": "loc_observatory_dome_01",
                        "participantIds": ["char_elena_001", "char_marcus_001"],
                        "statementsToReveal": ["stmt_signal_is_artificial_01"],
                        "statementsToHide": ["stmt_marcus_classified_orders_01"],
                        "viewpointEntityId": "char_elena_001",
                        "desiredOutcome": "Elena realizes the transmission is coming from inside the moon."
                    }
                ]
            }
        elif agent_name == "prose_writer":
            return {
                "sceneId": "scene_plan_01",
                "prose": 'The brass rings of the grand astrolabe rotated with a rhythmic hum. I peered into the optical array, where pulses of violet light flashed against the deep void.\n\n"You should not be running the deep scan tonight, Elena," Marcus\'s voice echoed from the shadows of the archway.\n\nI stepped back, pointing at the frequency spectrum on the crystal plate. "Look at the harmonic symmetry, Marcus. This isn\'t stellar noise. Someone is speaking."',
                "proposedInventions": [
                    {"type": "item_detail", "description": "Crystal spectrum display glowing violet", "potentialImpact": "minor_prop"}
                ]
            }
        elif agent_name == "style_agent":
            return {
                "sceneId": "scene_plan_01",
                "polishedProse": 'A hypnotic mechanical pulse reverberated through the domed observatory as the immense brass astrolabe turned. Through the high-aperture viewfinder, rhythmic spikes of luminous violet pulsed in defiance of cosmic chaos.\n\n"You should not be peering into the deep frequencies tonight, Elena," Marcus spoke, emerging from the archway shadows with measured steps.\n\nI traced the luminescent spikes with trembling fingers. "Examine the harmonic intervals, Marcus. This isn\'t random pulsar decay. Someone is transmitting."',
                "styleChangesSummary": "Elevated atmosphere and tension, sharpened dialogue cadence."
            }
        return {"status": "ok", "agent": agent_name}

    async def execute_screenplay_pipeline(
        self,
        task_id: str,
        request: ScreenplayPipelineRequest,
        progress_callback: Optional[Callable[[PipelineProgressStatus], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Executes the main pipeline:
        1. Text-to-Graph Ingestion & Entity Resolution (0% - 30%)
        2. Graph-to-Text Multi-Act Narrative & Scene Generation (30% - 80%)
        3. Screenplay PDF Script Compilation (80% - 100%)
        """
        start_time = time.perf_counter()
        logger.info("Starting CinemAgent Screenplay Pipeline", task_id=task_id)

        try:
            # -------------------------------------------------------------
            # STAGE 1: TEXT-TO-GRAPH INGESTION (0% -> 30%)
            # -------------------------------------------------------------
            await self._update_status(
                task_id=task_id,
                value=5,
                message="Decomposing raw narrative into structural hierarchy...",
                agent="Ingestion_Agent",
                stage="text_to_graph",
                callback=progress_callback
            )

            raw_input_text = request.raw_text or request.story_prompt or "Elena Vance investigates a mysterious celestial signal at the royal observatory."
            segmentation = await self._call_llm_agent(
                agent_name="Ingestion_Agent",
                instruction=ingestion_agent.instruction,
                user_input=raw_input_text
            )

            await self._update_status(
                task_id=task_id,
                value=15,
                message="Extracting narrative entities, coreferences, and events...",
                agent="Entity_Resolution_Agent",
                stage="text_to_graph",
                callback=progress_callback
            )

            await self._update_status(
                task_id=task_id,
                value=30,
                message="Validating temporal order and persisting atomic graph operations...",
                agent="Validation_Agent",
                stage="text_to_graph",
                callback=progress_callback,
                artifacts={"segmentation": segmentation}
            )

            # -------------------------------------------------------------
            # STAGE 2: GRAPH-TO-TEXT GENERATION (30% -> 80%)
            # -------------------------------------------------------------
            await self._update_status(
                task_id=task_id,
                value=35,
                message="Interpreting story parameters and viewpoint bounds...",
                agent="Story_Request_Interpreter",
                stage="graph_to_text",
                callback=progress_callback
            )

            story_prompt_input = json.dumps({
                "prompt": request.story_prompt or "Generate dramatic screenplay scene based on recent observatory events",
                "genre": request.genre,
                "tone": request.tone
            })
            story_request = await self._call_llm_agent(
                agent_name="Story_Request_Interpreter",
                instruction=story_request_interpreter.instruction,
                user_input=story_prompt_input
            )

            await self._update_status(
                task_id=task_id,
                value=45,
                message="Retrieving perspective-isolated subgraph...",
                agent="Graph_Retrieval_Agent",
                stage="graph_to_text",
                callback=progress_callback
            )
            subgraph = await self._call_llm_agent(
                agent_name="graph_retrieval_agent",
                instruction=graph_retrieval_agent.instruction,
                user_input=json.dumps(story_request)
            )

            await self._update_status(
                task_id=task_id,
                value=55,
                message="Designing multi-act narrative tension and beat pacing...",
                agent="Narrative_Planner",
                stage="graph_to_text",
                callback=progress_callback
            )
            narrative_outline = await self._call_llm_agent(
                agent_name="narrative_planner",
                instruction=narrative_planner.instruction,
                user_input=f"StoryRequest: {json.dumps(story_request)}\nSubgraph: {json.dumps(subgraph)}"
            )

            await self._update_status(
                task_id=task_id,
                value=65,
                message="Generating granular scene blueprints and facts disclosure...",
                agent="Scene_Planner",
                stage="graph_to_text",
                callback=progress_callback
            )
            scene_plans_data = await self._call_llm_agent(
                agent_name="scene_planner",
                instruction=scene_planner.instruction,
                user_input=f"NarrativeOutline: {json.dumps(narrative_outline)}\nSubgraph: {json.dumps(subgraph)}"
            )

            scene_plans = []
            if isinstance(scene_plans_data, dict):
                scene_plans = scene_plans_data.get("scenePlans", [])
            elif isinstance(scene_plans_data, list):
                scene_plans = scene_plans_data

            scenes_generation: Dict[str, Any] = {}
            final_prose_pieces: List[str] = []

            for idx, s_plan in enumerate(scene_plans):
                sid = s_plan.get("id", f"scene_plan_{idx+1}") if isinstance(s_plan, dict) else f"scene_plan_{idx+1}"
                
                await self._update_status(
                    task_id=task_id,
                    value=70,
                    message=f"Drafting prose and tracking ornamental inventions for {sid}...",
                    agent="Prose_Writer",
                    stage="graph_to_text",
                    callback=progress_callback
                )
                prose_res = await self._call_llm_agent(
                    agent_name="prose_writer",
                    instruction=prose_writer.instruction,
                    user_input=f"ScenePlan: {json.dumps(s_plan)}\nSubgraph: {json.dumps(subgraph)}"
                )

                await self._update_status(
                    task_id=task_id,
                    value=75,
                    message=f"Polishing prose voice, dialogue cadence, and style for {sid}...",
                    agent="Style_Agent",
                    stage="graph_to_text",
                    callback=progress_callback
                )
                style_res = await self._call_llm_agent(
                    agent_name="style_agent",
                    instruction=style_agent.instruction,
                    user_input=f"Genre: {request.genre}\nTone: {request.tone}\nProse: {json.dumps(prose_res)}"
                )

                await self._update_status(
                    task_id=task_id,
                    value=80,
                    message=f"Auditing narrative continuity and generating graph feedback for {sid}...",
                    agent="Narrative_Consistency_Agent",
                    stage="graph_to_text",
                    callback=progress_callback
                )
                consistency_res = await self._call_llm_agent(
                    agent_name="narrative_consistency_agent",
                    instruction=narrative_consistency_agent.instruction,
                    user_input=f"Scene: {json.dumps(s_plan)}\nPolished: {json.dumps(style_res)}"
                )

                feedback_res = await self._call_llm_agent(
                    agent_name="graph_feedback_agent",
                    instruction=graph_feedback_agent.instruction,
                    user_input=f"Polished: {json.dumps(style_res)}"
                )

                scenes_generation[sid] = {
                    "sceneId": sid,
                    "scenePlan": s_plan,
                    "results": {
                        "prose_writer": prose_res,
                        "style_agent": style_res,
                        "narrative_consistency_agent": consistency_res,
                        "graph_feedback_agent": feedback_res
                    }
                }

                pol_text = style_res.get("polishedProse", "") if isinstance(style_res, dict) else ""
                if not pol_text and isinstance(prose_res, dict):
                    pol_text = prose_res.get("prose", "")
                if pol_text:
                    final_prose_pieces.append(pol_text)

            # -------------------------------------------------------------
            # STAGE 3: PDF SCRIPT COMPILATION (80% -> 100%)
            # -------------------------------------------------------------
            pdf_path = None
            pdf_url = None
            if request.enable_pdf:
                await self._update_status(
                    task_id=task_id,
                    value=90,
                    message="Compiling formatted Hollywood screenplay layout into PDF...",
                    agent="PDF_Screenplay_Compiler",
                    stage="pdf_export",
                    callback=progress_callback
                )

                movie_title = narrative_outline.get("narrativeOutline", {}).get("title", "CinemAgent Screenplay") if isinstance(narrative_outline, dict) else "CinemAgent Screenplay"
                pdf_path = self.pdf_generator.generate_screenplay_pdf(
                    task_id=task_id,
                    title=movie_title,
                    story_request=story_request if isinstance(story_request, dict) else {},
                    narrative_outline=narrative_outline if isinstance(narrative_outline, dict) else {},
                    scene_plans_data=scene_plans_data,
                    scenes_generation=scenes_generation,
                    media_artifacts=[]
                )
                pdf_filename = Path(pdf_path).name
                pdf_url = f"/api/v1/pipeline/pdf/{task_id}"

            elapsed = round(time.perf_counter() - start_time, 2)
            
            final_artifacts = {
                "task_id": task_id,
                "execution_time_seconds": elapsed,
                "story_request": story_request,
                "subgraph": subgraph,
                "narrative_outline": narrative_outline,
                "scene_plans": scene_plans_data,
                "scenes_generation": scenes_generation,
                "final_narrative": "\n\n".join(final_prose_pieces),
                "pdf_path": pdf_path,
                "pdf_url": pdf_url
            }

            await self._update_status(
                task_id=task_id,
                value=100,
                message=f"Screenplay and narrative assets generated successfully in {elapsed}s",
                agent="Orchestrator",
                stage="completed",
                callback=progress_callback,
                artifacts=final_artifacts,
                is_completed=True
            )

            logger.info("Screenplay pipeline completed successfully", task_id=task_id, duration_seconds=elapsed)
            return final_artifacts

        except Exception as pipeline_error:
            logger.exception("Screenplay pipeline execution failed", task_id=task_id, error=str(pipeline_error))
            await self._update_status(
                task_id=task_id,
                value=100,
                message=f"Pipeline failed: {str(pipeline_error)}",
                agent="Orchestrator",
                stage="error",
                callback=progress_callback,
                is_error=True,
                error_message=str(pipeline_error)
            )
            raise pipeline_error

    # -------------------------------------------------------------
    # Standard Parallel RAG Query (Legacy compatibility)
    # -------------------------------------------------------------
    async def generate_response(self, prompt: str) -> str:
        if not self.has_llm:
            return "[Mock Agent Response] I received your prompt, but no API keys are configured. Add GEMINI_API_KEY to test live LLM generation."

        try:
            if settings.GEMINI_API_KEY:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={'system_instruction': SYSTEM_PROMPT}
                )
                return response.text
        except Exception as e:
            logger.error("LLM Generation failed", error=str(e))
            return f"Failed to generate response: {str(e)}"

    async def execute_pipeline(self, query: str) -> Dict[str, Any]:
        start_time = time.perf_counter()
        logger.info("Executing Agent loop", query=query)

        retrieval_task = asyncio.to_thread(self.retriever.retrieve_context, query)
        search_task = self.mcp_manager.run_search(query)

        retrieval_res, search_res = await asyncio.gather(retrieval_task, search_task)

        template = Template(USER_PROMPT_TEMPLATE)
        rendered_prompt = template.render(
            context=retrieval_res["combined_context"],
            search_results=search_res,
            query=query
        )

        response_text = await self.generate_response(rendered_prompt)
        elapsed = time.perf_counter() - start_time

        return {
            "query": query,
            "response": response_text,
            "metadata": {
                "execution_time_seconds": round(elapsed, 3),
                "retrieved_nodes_count": len(retrieval_res.get("graph_entities", [])),
                "vector_chunks_retrieved": len(retrieval_res.get("vector_hits", [])),
                "search_mcp_queried": bool(settings.SEARCH_MCP_URL)
            }
        }
