"""Focused narrative graph retrieval routes."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from ..dependencies import get_service, require_api_key
from ..models import SubgraphQuery
from ..service import NarrativeGraphService


router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.post("/{graph_id}/subgraph:query")
def query_subgraph(graph_id: UUID, request: SubgraphQuery, service: NarrativeGraphService = Depends(get_service)) -> dict[str, Any]:
    return service.query_subgraph(graph_id, request)
