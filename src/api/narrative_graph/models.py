"""Request and response contracts for the narrative graph API."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class OperationType(str, Enum):
    CREATE_ENTITY = "create_entity"
    CREATE_TIME = "create_time"
    CREATE_CONTEXT = "create_context"
    CREATE_EVENT = "create_event"
    CREATE_EVENT_PARTICIPANT = "create_event_participant"
    CREATE_KNOWLEDGE_ELEMENT = "create_knowledge_element"
    CREATE_ATTRIBUTE = "create_attribute"
    CREATE_STATEMENT = "create_statement"
    CREATE_RELATION = "create_relation"
    CREATE_EVENT_EFFECT = "create_event_effect"
    CREATE_EVENT_RELATION = "create_event_relation"
    CREATE_SOURCE_SEGMENT = "create_source_segment"
    CREATE_EVIDENCE = "create_evidence"
    LINK_EVIDENCE = "link_evidence"
    LINK_NODE_TO_CHAPTER = "link_node_to_chapter"
    UPDATE_ENTITY = "update_entity"
    UPDATE_EVENT = "update_event"
    UPDATE_NODE = "update_node"
    INVALIDATE_STATEMENT = "invalidate_statement"
    DELETE_NODE = "delete_node"
    MERGE_ENTITY = "merge_entity"


class NarrativeGraphCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)


class NarrativeGraphUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=500)


class NarrativeGraphResponse(BaseModel):
    id: UUID
    name: str
    version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    sequence: int | None = Field(default=None, ge=1)


class ChapterDocumentUpdate(BaseModel):
    document: dict[str, Any]
    plain_text: str = Field(max_length=2_000_000)
    revision: int = Field(ge=1)


class ChapterResponse(BaseModel):
    id: UUID
    graph_id: UUID
    title: str
    sequence: int
    revision: int
    document: dict[str, Any]
    plain_text: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChapterAnalysisResponse(BaseModel):
    id: UUID
    graph_id: UUID
    chapter_id: UUID
    chapter_revision: int
    status: str
    error: str | None = None


class TextProposal(BaseModel):
    id: str
    text: str
    rationale: str


class ProposalDecision(BaseModel):
    accepted_ids: list[UUID] = Field(default_factory=list, max_length=500)


class NarrativeOperation(BaseModel):
    id: UUID
    operation_type: OperationType
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    origin: Literal["agent", "writer"]

    @field_validator("payload")
    @classmethod
    def payload_must_not_be_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("operation payload cannot be empty")
        return value


class OperationBatchCreate(BaseModel):
    operations: list[NarrativeOperation] = Field(min_length=1, max_length=500)

    @field_validator("operations")
    @classmethod
    def unique_operation_ids(cls, value: list[NarrativeOperation]) -> list[NarrativeOperation]:
        if len({operation.id for operation in value}) != len(value):
            raise ValueError("operation IDs must be unique within a batch")
        return value


class OperationBatchResponse(BaseModel):
    id: UUID
    graph_id: UUID
    status: str
    operation_count: int
    error: str | None = None


class SubgraphQuery(BaseModel):
    entity_ids: list[UUID] = Field(default_factory=list, max_length=100)
    event_ids: list[UUID] = Field(default_factory=list, max_length=100)
    viewpoint_entity_id: UUID | None = None
    chapter_id: UUID | None = None
    include_evidence: bool = False
    limit: int = Field(default=100, ge=1, le=500)
