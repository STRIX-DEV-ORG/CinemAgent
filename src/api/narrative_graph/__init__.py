"""Narrative graph API package and backwards-compatible public imports."""
from fastapi import APIRouter

from .dependencies import get_service, require_api_key
from .models import (
    NarrativeGraphCreate,
    NarrativeGraphResponse,
    NarrativeOperation,
    OperationBatchCreate,
    OperationBatchResponse,
    OperationType,
    SubgraphQuery,
)
from .routers.graphs import router as graphs_router
from .routers.operations import router as operations_router
from .routers.retrieval import router as retrieval_router
from .service import NarrativeGraphService


router = APIRouter(tags=["narrative graphs"])
router.include_router(graphs_router)
router.include_router(operations_router)
router.include_router(retrieval_router)

__all__ = [
    "NarrativeGraphCreate",
    "NarrativeGraphResponse",
    "NarrativeGraphService",
    "NarrativeOperation",
    "OperationBatchCreate",
    "OperationBatchResponse",
    "OperationType",
    "SubgraphQuery",
    "get_service",
    "require_api_key",
    "router",
]
