"""Compatibility façade composed from focused narrative graph services."""
from typing import Any
from uuid import UUID

from src.db.clickhouse_client import get_clickhouse_client
from .models import (
    NarrativeGraphCreate,
    NarrativeGraphResponse,
    NarrativeGraphUpdate,
    OperationBatchCreate,
    OperationBatchResponse,
    SubgraphQuery,
)
from .services.batches import OperationBatchService
from .services.graphs import GraphService
from .services.materializer import OperationMaterializer
from .services.retrieval import SubgraphService
from .services.workspace import WorkspaceService
from .services.agents import AgentRunService


class NarrativeGraphService:
    """Preserves the public service interface while delegating by responsibility."""

    def __init__(self, client: Any | None = None) -> None:
        self.client = client if client is not None else get_clickhouse_client()
        self.graphs = GraphService(self.client)
        self.batches = OperationBatchService(self.client, self.graphs)
        self.materializer = OperationMaterializer(self.client)
        self.retrieval = SubgraphService(self.client, self.graphs)
        self.workspace = WorkspaceService(self.client, self.graphs)
        self.agents = AgentRunService(self.client, self.workspace, self.graphs)

    def create_graph(self, request: NarrativeGraphCreate) -> NarrativeGraphResponse:
        return self.graphs.create_graph(request)

    def get_graph(self, graph_id: UUID) -> NarrativeGraphResponse:
        return self.graphs.get_graph(graph_id)

    def update_graph(self, graph_id: UUID, request: NarrativeGraphUpdate) -> NarrativeGraphResponse:
        return self.graphs.update_graph(graph_id, request)

    def delete_graph(self, graph_id: UUID) -> None:
        self.graphs.delete_graph(graph_id)

    def submit_batch(self, graph_id: UUID, idempotency_key: str, batch: OperationBatchCreate) -> OperationBatchResponse:
        return self.batches.submit_batch(graph_id, idempotency_key, batch)

    def get_batch(self, graph_id: UUID, batch_id: UUID) -> OperationBatchResponse:
        return self.batches.get_batch(graph_id, batch_id)

    def materialize_batch(self, graph_id: UUID, batch_id: UUID) -> None:
        self.materializer.materialize_batch(graph_id, batch_id)

    def query_subgraph(self, graph_id: UUID, request: SubgraphQuery) -> dict[str, Any]:
        return self.retrieval.query_subgraph(graph_id, request)
