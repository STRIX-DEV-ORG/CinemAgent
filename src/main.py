import os
import uuid
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
    orchestrator = get_orchestrator()
    logger.info("Agent orchestrator initialized.")
    
    yield
    
    # Shutdown actions
    logger.info("Shutting down CinemAgent...")
    if orchestrator and orchestrator.mcp_manager:
        await orchestrator.mcp_manager.close_all()


app = FastAPI(
    title="CinemAgent API",
    description="Multi-Agent AI Screenplay, Knowledge Graph, Scenographer, Dialoger TTS, and Historical Investigator Production Suite.",
    version="0.3.0",
    lifespan=lifespan
)
app.include_router(narrative_graph_router)

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
    """
    Starts the full end-to-end multi-agent pipeline asynchronously:
    - Text-to-Graph Analysis (0 - 30%)
    - Graph-to-Text Multi-Act Narrative & Scene Generation (30 - 80%)
    - Screenplay PDF Compilation: PyPDF + ReportLab (80 - 100%)
    """
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    
    initial_status = PipelineProgressStatus(
        task_id=task_id,
        status_value=0,
        status_message="Screenplay generation task queued...",
        current_agent="Orchestrator",
        stage="queued"
    )
    task_progress_store[task_id] = initial_status

    async def run_pipeline_job():
        try:
            orch = get_orchestrator()
            await orch.execute_screenplay_pipeline(task_id=task_id, request=request)
        except Exception as e:
            logger.error("Background screenplay pipeline task failed", task_id=task_id, error=str(e))

    background_tasks.add_task(run_pipeline_job)
    return initial_status


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

@app.get("/api/v1/pipeline/status/{task_id}", response_model=PipelineProgressStatus)
def get_pipeline_status(task_id: str):
    """
    Polls the real-time progress status (0-100), active agent, stage, and artifacts.
    """
    status = task_progress_store.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task ID '{task_id}' not found.")
    return status


@app.get("/api/v1/pipeline/stream/{task_id}")
async def stream_pipeline_status(task_id: str):
    """
    Server-Sent Events (SSE) stream for real-time progress updates (0 to 100%).
    """
    if task_id not in task_progress_store:
        raise HTTPException(status_code=404, detail=f"Task ID '{task_id}' not found.")

    async def event_generator():
        last_val = -1
        last_msg = ""
        while True:
            status = task_progress_store.get(task_id)
            if not status:
                break

            if status.status_value != last_val or status.status_message != last_msg:
                last_val = status.status_value
                last_msg = status.status_message
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
            mime_type = "image/png" if filename.endswith(".png") else ("audio/wav" if filename.endswith(".wav") else "application/octet-stream")
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
