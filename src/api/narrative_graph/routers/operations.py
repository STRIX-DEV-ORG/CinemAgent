"""Operation journal routes for narrative graph writes."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status

from ..dependencies import get_service, require_api_key
from ..models import OperationBatchCreate, OperationBatchResponse
from ..service import NarrativeGraphService


router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.post("/{graph_id}/operation-batches", response_model=OperationBatchResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_operation_batch(graph_id: UUID, request: OperationBatchCreate, background_tasks: BackgroundTasks,
                           idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
                           service: NarrativeGraphService = Depends(get_service)) -> OperationBatchResponse:
    response = service.submit_batch(graph_id, idempotency_key, request)
    if response.status == "accepted":
        background_tasks.add_task(service.materialize_batch, graph_id, response.id)
    return response


@router.get("/{graph_id}/operation-batches/{batch_id}", response_model=OperationBatchResponse)
def get_operation_batch(graph_id: UUID, batch_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> OperationBatchResponse:
    return service.get_batch(graph_id, batch_id)
