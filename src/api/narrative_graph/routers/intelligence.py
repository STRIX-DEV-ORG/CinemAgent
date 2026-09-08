"""Writer intelligence and technical ClickHouse observability endpoints."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ..dependencies import get_service, require_admin_api_key, require_api_key
from ..service import NarrativeGraphService


router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.get("/{graph_id}/events")
def events(graph_id: UUID, chapter_id: UUID | None = None, limit: int = Query(default=100, ge=1, le=500), service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    return service.intelligence.events(graph_id, chapter_id, limit)


@router.post("/{graph_id}/semantic-index:backfill", status_code=202)
def backfill_semantic_index(graph_id: UUID, background_tasks: BackgroundTasks, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    background_tasks.add_task(service.intelligence.backfill_canon, graph_id)
    return {"status": "accepted", "message": "Canon indexing started"}


@router.post("/{graph_id}/events:backfill", status_code=202)
def backfill_events(graph_id: UUID, background_tasks: BackgroundTasks, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    background_tasks.add_task(service.intelligence.backfill_legacy_events, graph_id)
    return {"status": "accepted", "message": "Legacy narrative history backfill started"}


@router.get("/{graph_id}/semantic-search")
def semantic_search(graph_id: UUID, query: str, chapter_id: UUID | None = None,
                    source_type: list[str] = Query(default=[]), limit: int = Query(default=10, ge=1, le=50),
                    service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    return service.intelligence.semantic_search(graph_id, query, chapter_id, source_type or None, limit)


@router.get("/{graph_id}/intelligence/story-health")
def story_health(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> dict:
    return service.intelligence.story_health(graph_id)


@router.get("/{graph_id}/intelligence/character-presence")
def character_presence(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    return service.intelligence.character_presence(graph_id)


@router.get("/{graph_id}/intelligence/relation-timeline")
def relation_timeline(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    return service.intelligence.relation_timeline(graph_id)


@router.get("/{graph_id}/intelligence/metrics")
def metrics(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> dict:
    return service.intelligence.metrics(graph_id)


@router.get("/{graph_id}/diagnostics/projection", dependencies=[Depends(require_admin_api_key)])
def projection_status(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    return service.projections.status(graph_id)


@router.post("/{graph_id}/diagnostics/projection:replay", dependencies=[Depends(require_admin_api_key)], status_code=202)
def replay_projection(graph_id: UUID, background_tasks: BackgroundTasks, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    background_tasks.add_task(service.projections.project_graph, graph_id)
    return {"status": "accepted", "message": "Projection replay started"}


@router.post("/{graph_id}/diagnostics/projection:rebuild", dependencies=[Depends(require_admin_api_key)], status_code=202)
def rebuild_projection(graph_id: UUID, background_tasks: BackgroundTasks, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    background_tasks.add_task(service.projections.rebuild, graph_id)
    return {"status": "accepted", "message": "Projection rebuild started"}


@router.get("/{graph_id}/diagnostics/projection:parity", dependencies=[Depends(require_admin_api_key)])
def projection_parity(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    return service.projections.parity(graph_id)


@router.put("/{graph_id}/diagnostics/projected-reads", dependencies=[Depends(require_admin_api_key)])
def projected_reads(graph_id: UUID, enabled: bool, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    try:
        return service.projections.set_projected_reads(graph_id, enabled)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{graph_id}/diagnostics/projection:bootstrap", dependencies=[Depends(require_admin_api_key)], status_code=202)
def bootstrap_projection(graph_id: UUID, background_tasks: BackgroundTasks, service: NarrativeGraphService = Depends(get_service)) -> dict:
    service.graphs.get_graph(graph_id)
    background_tasks.add_task(service.projections.bootstrap_from_legacy, graph_id)
    return {"status": "accepted", "message": "Legacy projection bootstrap started"}


@router.get("/diagnostics/clickhouse", dependencies=[Depends(require_admin_api_key)])
def clickhouse_diagnostics(service: NarrativeGraphService = Depends(get_service)) -> dict:
    return service.intelligence.diagnostics()
