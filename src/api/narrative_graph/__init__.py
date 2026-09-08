"""Narrative graph API package and backwards-compatible public imports."""
from fastapi import APIRouter

from .dependencies import get_service, require_api_key
from .models import (
    NarrativeGraphCreate,
    NarrativeGraphResponse,
    NarrativeGraphUpdate,
    NarrativeOperation,
    OperationBatchCreate,
    OperationBatchResponse,
    OperationType,
    SubgraphQuery,
    TextProposal,
)
from .routers.graphs import router as graphs_router
from .routers.operations import router as operations_router
from .routers.retrieval import router as retrieval_router
from .routers.workspace import router as workspace_router
from .service import NarrativeGraphService


router = APIRouter(tags=["narrative graphs"])
router.include_router(graphs_router)
router.include_router(operations_router)
router.include_router(retrieval_router)
router.include_router(workspace_router)

__all__ = [
    "NarrativeGraphCreate",
    "NarrativeGraphResponse",
    "NarrativeGraphUpdate",
    "NarrativeGraphService",
    "NarrativeOperation",
    "OperationBatchCreate",
    "OperationBatchResponse",
    "OperationType",
    "SubgraphQuery",
    "TextProposal",
    "get_service",
    "require_api_key",
    "router",
]
