"""Writer workspace routes for chapters, documents, and analysis proposals."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from ..dependencies import get_service, require_api_key
from ..models import (ChapterAnalysisResponse, ChapterCreate, ChapterDocumentUpdate, ChapterOrderUpdate, ChapterResponse,
                      ChapterUpdate, NarrativeOperation, OperationBatchCreate, OperationBatchResponse,
                      ProposalDecision, TextProposal)
from ..service import NarrativeGraphService

router = APIRouter(prefix="/v1/narrative-graphs", dependencies=[Depends(require_api_key)])


@router.get("/{graph_id}/chapters", response_model=list[ChapterResponse])
def list_chapters(graph_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> list[ChapterResponse]:
    return service.workspace.list_chapters(graph_id)


@router.post("/{graph_id}/chapters", response_model=ChapterResponse, status_code=status.HTTP_201_CREATED)
def create_chapter(graph_id: UUID, request: ChapterCreate, service: NarrativeGraphService = Depends(get_service)) -> ChapterResponse:
    return service.workspace.create_chapter(graph_id, request)


@router.put("/{graph_id}/chapters/order", response_model=list[ChapterResponse])
def reorder_chapters(graph_id: UUID, request: ChapterOrderUpdate,
                     service: NarrativeGraphService = Depends(get_service)) -> list[ChapterResponse]:
    return service.workspace.reorder_chapters(graph_id, request)


@router.get("/{graph_id}/chapters/{chapter_id}", response_model=ChapterResponse)
def get_chapter(graph_id: UUID, chapter_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> ChapterResponse:
    return service.workspace.get_chapter(graph_id, chapter_id)


@router.delete("/{graph_id}/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(graph_id: UUID, chapter_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> None:
    service.workspace.delete_chapter(graph_id, chapter_id)


@router.patch("/{graph_id}/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter(graph_id: UUID, chapter_id: UUID, request: ChapterUpdate, service: NarrativeGraphService = Depends(get_service)) -> ChapterResponse:
    return service.workspace.update_chapter(graph_id, chapter_id, request)


@router.put("/{graph_id}/chapters/{chapter_id}/document", response_model=ChapterResponse)
def update_chapter_document(graph_id: UUID, chapter_id: UUID, request: ChapterDocumentUpdate,
                            service: NarrativeGraphService = Depends(get_service)) -> ChapterResponse:
    return service.workspace.update_document(graph_id, chapter_id, request)


@router.post("/{graph_id}/chapters/{chapter_id}/analysis-runs", response_model=ChapterAnalysisResponse, status_code=status.HTTP_201_CREATED)
def start_analysis(graph_id: UUID, chapter_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> ChapterAnalysisResponse:
    return service.workspace.start_analysis(graph_id, chapter_id)


@router.post("/{graph_id}/chapters/{chapter_id}/text-proposals", response_model=list[TextProposal])
def suggest_text(graph_id: UUID, chapter_id: UUID,
                 service: NarrativeGraphService = Depends(get_service)) -> list[TextProposal]:
    return service.workspace.suggest_text(graph_id, chapter_id)


@router.get("/{graph_id}/chapters/{chapter_id}/analysis-runs/{run_id}/proposals")
def get_proposals(graph_id: UUID, chapter_id: UUID, run_id: UUID, service: NarrativeGraphService = Depends(get_service)) -> list[dict]:
    return service.workspace.get_proposals(graph_id, chapter_id, run_id)


@router.post("/{graph_id}/chapters/{chapter_id}/analysis-runs/{run_id}:apply", response_model=OperationBatchResponse, status_code=status.HTTP_202_ACCEPTED)
def apply_proposals(graph_id: UUID, chapter_id: UUID, run_id: UUID, request: ProposalDecision, background_tasks: BackgroundTasks,
                    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
                    service: NarrativeGraphService = Depends(get_service)) -> OperationBatchResponse:
    proposals = service.workspace.get_proposals(graph_id, chapter_id, run_id)
    accepted = {str(item) for item in request.accepted_ids}
    operations = []
    for proposal in proposals:
        if str(proposal["id"]) not in accepted or proposal["status"] != "proposed":
            continue
        for operation in proposal["payload"]["operations"]:
            operations.append(NarrativeOperation(id=UUID(operation["id"]), operation_type=operation["operation_type"],
                                                 payload=operation["payload"], provenance=proposal["provenance"], origin="agent"))
    if not operations:
        raise HTTPException(status_code=422, detail="select at least one proposed operation")
    # Relations may reference nodes proposed in a separate card. Materialize
    # all node records before their connecting edges regardless of proposal ID.
    operation_order = {
        "create_entity": 0, "create_event": 0, "create_context": 0, "create_knowledge_element": 0,
        "create_relation": 1, "create_statement": 2, "link_node_to_chapter": 3,
        "create_evidence": 3, "link_evidence": 4,
    }
    operations.sort(key=lambda operation: operation_order.get(operation.operation_type.value, 2))
    response = service.submit_batch(graph_id, idempotency_key, OperationBatchCreate(operations=operations))
    service.workspace.mark_proposals(graph_id, chapter_id, run_id, request.accepted_ids, "accepted")
    if response.status == "accepted":
        background_tasks.add_task(service.materialize_batch, graph_id, response.id)
    return response
