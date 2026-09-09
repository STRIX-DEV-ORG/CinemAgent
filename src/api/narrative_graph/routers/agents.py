"""Contextual agent-run endpoints used by the writer workspace."""
import asyncio
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import StreamingResponse

from ..dependencies import get_service, require_api_key
from src.config import settings
from ..models import AgentRunCreate, AgentRunResponse, AgentRunReview, StoryboardDecision
from ..service import NarrativeGraphService

router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.post("/{graph_id}/agent-runs", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_run(graph_id: UUID, request: AgentRunCreate, background_tasks: BackgroundTasks,
                          service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    run = service.agents.start(graph_id, request)
    if settings.NARRATIVE_AGENT_WORKER_IN_PROCESS:
        background_tasks.add_task(service.agents.execute, graph_id, run.id)
    return run


@router.get("/{graph_id}/agent-runs", response_model=list[AgentRunResponse])
def list_agent_runs(graph_id: UUID, chapter_id: UUID | None = None,
                    service: NarrativeGraphService = Depends(get_service)) -> list[AgentRunResponse]:
    return service.agents.list(graph_id, chapter_id)


@router.get("/{graph_id}/agent-runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(graph_id: UUID, run_id: UUID,
                  service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    return service.agents.get(graph_id, run_id)


@router.post("/{graph_id}/agent-runs/{run_id}:cancel", response_model=AgentRunResponse)
def cancel_agent_run(graph_id: UUID, run_id: UUID,
                     service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    return service.agents.cancel(graph_id, run_id)


@router.post("/{graph_id}/agent-runs/{run_id}:retry", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_agent_run(graph_id: UUID, run_id: UUID, background_tasks: BackgroundTasks,
                    service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    run = service.agents.retry(graph_id, run_id)
    if settings.NARRATIVE_AGENT_WORKER_IN_PROCESS:
        background_tasks.add_task(service.agents.execute, graph_id, run_id)
    return run


@router.get("/{graph_id}/agent-runs/{run_id}/stream")
async def stream_agent_run(graph_id: UUID, run_id: UUID,
                           service: NarrativeGraphService = Depends(get_service)) -> StreamingResponse:
    """Emit durable run state until the asynchronous writer tool reaches a terminal state."""
    service.agents.get(graph_id, run_id)

    async def events():
        last = None
        while True:
            run = service.agents.get(graph_id, run_id)
            payload = run.model_dump_json()
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if run.status in {"completed", "failed", "reviewed", "cancelled"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/{graph_id}/agent-runs/{run_id}/artifacts")
def get_agent_artifacts(graph_id: UUID, run_id: UUID,
                        service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    """List durable media/report metadata; storage URLs are returned verbatim."""
    return service.agents.artifacts(graph_id, run_id)


@router.post("/{graph_id}/agent-runs/{run_id}/review", response_model=AgentRunResponse)
def review_agent_run(graph_id: UUID, run_id: UUID, request: AgentRunReview,
                     service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    return service.agents.review(graph_id, run_id, request)


@router.post("/{graph_id}/agent-runs/{run_id}/storyboards", response_model=AgentRunResponse)
def save_storyboards(graph_id: UUID, run_id: UUID, request: StoryboardDecision,
                     service: NarrativeGraphService = Depends(get_service)) -> AgentRunResponse:
    """Persist only the storyboard images explicitly selected by the writer."""
    return service.agents.save_storyboards(graph_id, run_id, request.selected_scene_ids)
