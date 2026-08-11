from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime


class DocumentChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: str
    chunk_index: int
    content: str
    embedding: List[float]
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KGNode(BaseModel):
    id: str  # Unique identifier (e.g. "movie_matrix", "person_keanu_reeves")
    name: str
    type: str  # e.g., "Movie", "Actor", "Director", "Genre"
    description: Optional[str] = ""
    embedding: Optional[List[float]] = None
    properties: Dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class KGEdge(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: str
    target_id: str
    relation: str  # e.g., "ACTED_IN", "DIRECTED", "PREQUEL_OF"
    description: Optional[str] = ""
    weight: float = 1.0
    properties: Dict[str, str] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GraphQueryResponse(BaseModel):
    nodes: List[KGNode]
    edges: List[KGEdge]
