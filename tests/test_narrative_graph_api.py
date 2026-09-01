from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.narrative_graph import (
    NarrativeGraphService,
    NarrativeOperation,
    OperationBatchCreate,
    OperationType,
    router,
)
from src.api.narrative_graph.services.materializer import OperationMaterializer


class Result:
    def __init__(self, columns, rows):
        self.column_names = columns
        self.result_rows = rows


def test_narrative_graph_router_exposes_all_public_paths():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    graph_id = str(uuid4())

    requests = [
        ("post", "/v1/narrative-graphs", {"name": "Test graph"}),
        ("get", f"/v1/narrative-graphs/{graph_id}", None),
        ("post", f"/v1/narrative-graphs/{graph_id}/operation-batches", {"operations": []}),
        ("get", f"/v1/narrative-graphs/{graph_id}/operation-batches/{uuid4()}", None),
        ("post", f"/v1/narrative-graphs/{graph_id}/subgraph:query", {}),
    ]
    for method, path, payload in requests:
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401


def test_submit_batch_journals_operations_and_replays_idempotency_key():
    graph_id = uuid4()
    operation_id = uuid4()
    client = Mock()
    client.query.side_effect = [
        Result(["id", "name", "version", "created_at", "updated_at"], [[graph_id, "Story", 1, None, None]]),
        Result(["id", "status", "operation_count", "error"], []),
        Result(["id", "name", "version", "created_at", "updated_at"], [[graph_id, "Story", 1, None, None]]),
        Result(["id", "status", "operation_count", "error"], [[uuid4(), "accepted", 1, None]]),
    ]
    service = NarrativeGraphService(client)
    batch = OperationBatchCreate(operations=[NarrativeOperation(
        id=operation_id,
        operation_type=OperationType.CREATE_ENTITY,
        payload={"id": str(uuid4()), "name": "Elena", "type": "character", "status": "active", "metadata": {}},
        origin="agent",
    )])

    first = service.submit_batch(graph_id, "request-1", batch)
    replay = service.submit_batch(graph_id, "request-1", batch)

    assert first.status == "accepted"
    assert replay.status == "accepted"
    assert client.insert.call_count == 2
    assert client.insert.call_args_list[0].args[0] == "operation_batch"
    assert client.insert.call_args_list[1].args[0] == "graph_operation"


def test_batch_rejects_payload_scoped_to_another_graph():
    graph_id = uuid4()
    client = Mock()
    client.query.return_value = Result(["id", "name", "version", "created_at", "updated_at"], [[graph_id, "Story", 1, None, None]])
    service = NarrativeGraphService(client)
    batch = OperationBatchCreate(operations=[NarrativeOperation(
        id=uuid4(),
        operation_type=OperationType.CREATE_ENTITY,
        payload={"id": str(uuid4()), "graph_id": str(uuid4()), "name": "Elena"},
        origin="agent",
    )])

    try:
        service.submit_batch(graph_id, "request-2", batch)
    except Exception as error:
        assert getattr(error, "status_code", None) == 422
    else:
        raise AssertionError("expected graph scope validation to reject the batch")


def test_materializer_applies_entity_creation_to_canonical_table():
    graph_id = uuid4()
    entity_id = uuid4()
    client = Mock()

    OperationMaterializer(client)._apply_operation({
        "graph_id": graph_id,
        "operation_type": OperationType.CREATE_ENTITY.value,
        "payload": {"id": str(entity_id), "name": "Elena", "type": "character", "status": "active", "metadata": {}},
    })

    assert client.insert.call_args.args[0] == "entity"
    assert "graph_id" in client.insert.call_args.kwargs["column_names"]
