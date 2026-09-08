"""Narrative graph lifecycle routes."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status

from ..dependencies import get_service, require_api_key
from ..models import NarrativeGraphCreate, NarrativeGraphResponse, NarrativeGraphUpdate
from ..service import NarrativeGraphService


router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.post("", response_model=NarrativeGraphResponse, status_code=status.HTTP_201_CREATED)
def create_narrative_graph(request: NarrativeGraphCreate, service: NarrativeGraphService = Depends(get_service)) -> NarrativeGraphResponse:
    return service.create_graph(request)


@router.get("/{graph_id}", response_model=NarrativeGraphResponse)
def get_narrative_graph(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> NarrativeGraphResponse:
    return service.get_graph(graph_id)


@router.patch("/{graph_id}", response_model=NarrativeGraphResponse)
def update_narrative_graph(graph_id: UUID, request: NarrativeGraphUpdate,
                           service: NarrativeGraphService = Depends(get_service)) -> NarrativeGraphResponse:
    return service.update_graph(graph_id, request)


@router.delete("/{graph_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_narrative_graph(
	graph_id: UUID,
	background_tasks: BackgroundTasks,
	service: NarrativeGraphService = Depends(get_service),
) -> None:
	# Confirm the story exists while the request is active, then let ClickHouse
	# finish its many table mutations after the UI has been released.
	service.get_graph(graph_id)
	background_tasks.add_task(service.delete_graph, graph_id)
