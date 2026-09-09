import os
import uuid
from uuid import UUID
import uvicorn
import asyncio
import structlog
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import settings
from src.db.clickhouse_client import init_db, get_clickhouse_client
from src.agent.orchestrator import AgentOrchestrator, task_progress_store
from src.api.narrative_graph.models import AgentRunCreate
from src.agent.scenographer_agent import scenographer_executor
from src.agent.dialogue_tts_agent import dialogue_tts_executor
from src.agent.searcher_agent import searcher_investigator_executor
from src.agent.models import (
    ScreenplayPipelineRequest,
    PipelineProgressStatus,
    ScenographerRequest,
    ScenographerResponse,
    DialogerRequest,
    DialogerResponse,
    InvestigatorRequest,
    InvestigatorResponse
)
from src.api.narrative_graph import router as narrative_graph_router
from src.api.narrative_graph.service import NarrativeGraphService
from src.api.media import router as media_router

# Setup structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Orchestrator lazy/startup initialization
orchestrator: AgentOrchestrator = None


def get_orchestrator() -> AgentOrchestrator:
    global orchestrator
    if orchestrator is None:
        orchestrator = AgentOrchestrator()
    return orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    global orchestrator
    logger.info("Starting up CinemAgent web application...")
    
    # 1. Initialize ClickHouse schemas
    try:
        init_db()
    except Exception as e:
        logger.error("ClickHouse startup initialization failed", error=str(e))
        
    # 2. Instantiate Orchestrator
    try:
        orchestrator = AgentOrchestrator()
        logger.info("Agent orchestrator initialized.")
    except Exception as e:
        logger.warning("Agent orchestrator startup initialization deferred", error=str(e))
    
    async def projection_loop() -> None:
        """Resume event projection after restarts; checkpoints make retries safe."""
        while True:
            try:
                await asyncio.to_thread(NarrativeGraphService().projections.project_pending)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Narrative projection pass failed", error=str(error))
            await asyncio.sleep(3)

    projection_task = asyncio.create_task(projection_loop()) if settings.NARRATIVE_PROJECTOR_IN_PROCESS else None
    yield
    
    # Shutdown actions
    logger.info("Shutting down CinemAgent...")
    if projection_task:
        projection_task.cancel()
        try:
            await projection_task
        except asyncio.CancelledError:
            pass
    if orchestrator and hasattr(orchestrator, 'mcp_manager') and orchestrator.mcp_manager:
        await orchestrator.mcp_manager.close_all()


app = FastAPI(
    title="CinemAgent API",
    description="Multi-Agent AI Screenplay, Knowledge Graph, Scenographer, Dialoger TTS, and Historical Investigator Production Suite.",
    version="0.3.0",
    lifespan=lifespan
)
app.include_router(narrative_graph_router)
app.include_router(media_router)

# Enable CORS for web frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# 1. Main Orchestrator End-to-End Execution
# -----------------------------------------------------------------------------

@app.post("/api/v1/orchestrator/run", response_model=PipelineProgressStatus)
@app.post("/api/v1/pipeline/generate", response_model=PipelineProgressStatus)
async def generate_screenplay_pipeline(
    request: ScreenplayPipelineRequest,
    background_tasks: BackgroundTasks
):
    """Compatibility entrypoint backed by the durable contextual writer run."""
    if not request.graph_id:
        raise HTTPException(status_code=422, detail="graph_id is required. Create or select a story, then run production against that story.")
    service = NarrativeGraphService()
    run = service.agents.start(request.graph_id, AgentRunCreate(
        agent_group="produce", chapter_id=request.chapter_id,
        scope="chapter" if request.chapter_id else "story",
        instruction=request.story_prompt or request.raw_text or "",
        options={"enable_images": request.enable_images, "enable_tts": request.enable_tts,
                 "enable_pdf": request.enable_pdf, "genre": request.genre, "tone": request.tone},
    ))
    if settings.NARRATIVE_AGENT_WORKER_IN_PROCESS:
        background_tasks.add_task(service.agents.execute, request.graph_id, run.id)
    return PipelineProgressStatus(task_id=str(run.id), status_value=run.progress, status_message=run.message,
                                  current_agent="WriterOrchestrator", stage="queued")


# -----------------------------------------------------------------------------
# 2. Standalone Scenographer Agent (UI Single-Click Button)
# -----------------------------------------------------------------------------

@app.post("/api/v1/agents/scenographer", response_model=ScenographerResponse)
async def run_standalone_scenographer(request: ScenographerRequest):
    """
    Executes the Scenographer Agent individually outside of the pipeline.
    Translates a chapter / scene script text and segment IDs into cinematic storyboard images.
    """
    if not request.chapter_text.strip():
        raise HTTPException(status_code=400, detail="Chapter text cannot be empty.")

    try:
        result = await scenographer_executor.execute(request)
        return result
    except Exception as e:
        logger.exception("Scenographer agent execution failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Scenographer generation failed: {str(e)}")


# -----------------------------------------------------------------------------
# 3. Standalone Dialoger / Dialogue TTS Agent (UI Single-Click Button)
# -----------------------------------------------------------------------------

@app.post("/api/v1/agents/dialoger", response_model=DialogerResponse)
@app.post("/api/v1/agents/dialogue-tts", response_model=DialogerResponse)
async def run_standalone_dialoger(request: DialogerRequest):
    """
    Executes the Dialoger (Gemini Flash TTS) Agent individually outside of the pipeline.
    Extracts all character dialogue lines from a script/chapter and synthesizes voiced audio samples.
    """
    if not request.chapter_text.strip():
        raise HTTPException(status_code=400, detail="Chapter text cannot be empty.")

    try:
        result = await dialogue_tts_executor.execute(request)
        return result
    except Exception as e:
        logger.exception("Dialoger agent execution failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Dialogue TTS generation failed: {str(e)}")


# -----------------------------------------------------------------------------
# 4. Standalone Searcher / Historical Investigator Agent (UI Single-Click Button)
# -----------------------------------------------------------------------------

@app.post("/api/v1/agents/searcher", response_model=InvestigatorResponse)
@app.post("/api/v1/agents/investigator", response_model=InvestigatorResponse)
async def run_standalone_investigator(request: InvestigatorRequest):
    """
    Executes the Historical Investigator & Lore Searcher Agent on a text query.
    Performs historical fact-checking, anachronism detection, and offers writer recommendations.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Investigation query cannot be empty.")

    try:
        result = await searcher_investigator_executor.execute(request)
        return result
    except Exception as e:
        logger.exception("Investigator agent execution failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Historical investigation failed: {str(e)}")


# -----------------------------------------------------------------------------
# 5. Status, Streaming, Media, and PDF Endpoints
# -----------------------------------------------------------------------------

def _durable_pipeline_status(graph_id: UUID, task_id: str) -> PipelineProgressStatus:
    run = NarrativeGraphService().agents.get(graph_id, UUID(task_id))
    return PipelineProgressStatus(task_id=task_id, status_value=run.progress, status_message=run.message,
        current_agent=run.stages[-1].name if run.stages else "WriterOrchestrator",
        stage=run.stages[-1].status if run.stages else run.status,
        is_completed=run.status in {"completed", "reviewed"}, is_error=run.status in {"failed", "cancelled"},
        error_message=run.error, artifacts=run.result)


@app.get("/api/v1/pipeline/status/{task_id}", response_model=PipelineProgressStatus)
def get_pipeline_status(task_id: str, graph_id: UUID):
    """
    Polls the real-time progress status (0-100), active agent, stage, and artifacts.
    """
    return _durable_pipeline_status(graph_id, task_id)


@app.get("/api/v1/pipeline/stream/{task_id}")
async def stream_pipeline_status(task_id: str, graph_id: UUID):
    """
    Server-Sent Events (SSE) stream for real-time progress updates (0 to 100%).
    """
    async def event_generator():
        last = None
        while True:
            status = _durable_pipeline_status(graph_id, task_id)
            if status.model_dump_json() != last:
                last = status.model_dump_json()
                data_json = status.model_dump_json()
                yield f"data: {data_json}\n\n"
            if status.is_completed or status.is_error:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/pipeline/pdf/{task_id}")
def download_screenplay_pdf(task_id: str):
    """
    Downloads the compiled Screenplay PDF document.
    """
    status = task_progress_store.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task ID '{task_id}' not found.")

    pdf_path = status.artifacts.get("pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        fallback_path = f"artifacts/pdf/CinemAgent_Script_{task_id}.pdf"
        if os.path.exists(fallback_path):
            pdf_path = fallback_path
        else:
            raise HTTPException(status_code=404, detail="PDF has not completed generating yet or was not found.")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"CinemAgent_Screenplay_{task_id}.pdf"
    )


@app.get("/api/v1/pipeline/media/{filename}")
def get_media_asset(filename: str):
    """
    Serves generated Scenographer storyboard images or Flash TTS dialogue audio files.
    """
    search_paths = [
        Path("artifacts/media/images") / filename,
        Path("artifacts/media/audio") / filename,
        Path("artifacts/pdf") / filename
    ]

    for p in search_paths:
        if p.exists():
            mime_type = "image/png" if filename.endswith(".png") else ("audio/wav" if filename.endswith(".wav") else ("audio/mpeg" if filename.endswith(".mp3") else "application/octet-stream"))
            return FileResponse(path=str(p), media_type=mime_type)

    raise HTTPException(status_code=404, detail=f"Media file '{filename}' not found.")


# -----------------------------------------------------------------------------
# General Query & RAG Endpoints (Legacy Compatibility)
# -----------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    response: str
    metadata: dict


@app.get("/health")
def health_check():
    """
    Checks connection to ClickHouse database.
    """
    try:
        client = get_clickhouse_client()
        is_alive = client.ping()
        if not is_alive:
            raise HTTPException(status_code=503, detail="ClickHouse did not ping successfully")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {"status": "degraded", "database": "disconnected", "error": str(e)}


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Post a search or analytics query to CinemAgent.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty")
        
    try:
        orch = get_orchestrator()
        result = await orch.execute_pipeline(request.query)
        return QueryResponse(
            query=result["query"],
            response=result["response"],
            metadata=result["metadata"]
        )
    except Exception as e:
        logger.exception("Error executing user query", query=request.query)
        raise HTTPException(status_code=500, detail=f"Internal agent query error: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app)
