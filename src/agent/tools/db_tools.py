import secrets
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import json

#  Entities definition
class NarrativeEntity(str, Enum):
    NARRATIVE_GRAPH = "narrative_graph"
    ENTITY = "entity"
    TIME = "time"
    EVENT = "event"
    SOURCE_SEGMENT = "source_segment"
    ATTRIBUTE = "attribute"
    EVIDENCE = "evidence"
    EVENT_RELATION = "event_relation"
    EVENT_PARTICIPANT = "event_participant"
    CONTEXT = "context"
    KNOWLEDGE_ELEMENT = "knowledge_element"
    ELEMENT_EVIDENCE = "element_evidence"
    STATEMENT = "statement"
    EVENT_EFFECT = "event_effect"

class CRUDOperation(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

class NarrativeGraphCRUDInput(BaseModel):
    entity: NarrativeEntity = Field(
        ..., 
        description="The table/entity of the narrative graph on which the action will be executed."
    )
    operation: CRUDOperation = Field(
        ..., 
        description="Type of operation to perform: 'create', 'read', 'update' or 'delete'."
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Fields and values for 'create' or 'update'. For 'create' it must include all required fields."
    )
    record_id: Optional[str] = Field(
        default=None,
        description="Unique identifier (UUID/ID) of the record. Required for 'update' and 'delete' operations."
    )

#  Tool Handler
def execute_narrative_crud(
    entity: str, 
    operation: str, 
    data: Optional[Dict[str, Any]] = None, 
    record_id: Optional[str] = None
) -> str:
    """
        Executes CRUD operations on the narrative graph data.
    """
    data = data or {}
    
    # Validations of operational integrity
    if operation in [CRUDOperation.UPDATE, CRUDOperation.DELETE] and not record_id:
        return json.dumps({"status": "error", "message": f"'record_id' is required for operation '{operation}'."})
    
    if operation == CRUDOperation.CREATE and not data:
        return json.dumps({"status": "error", "message": "'data' payload is required for operation 'create'."})

    try:
        if operation == CRUDOperation.CREATE:
            # Replace with real ORM client / SQL Driver (e.g., SQLAlchemy, psycopg2)
            # result = db[entity].insert(data)
            return json.dumps({"status": "success", "operation": "create", "entity": entity, "inserted_data": data})

        elif operation == CRUDOperation.UPDATE:
            # result = db[entity].update_by_id(record_id, data)
            return json.dumps({"status": "success", "operation": "update", "entity": entity, "id": record_id, "updated_fields": data})

        elif operation == CRUDOperation.DELETE:
            # result = db[entity].delete_by_id(record_id)
            return json.dumps({"status": "success", "operation": "delete", "entity": entity, "id": record_id})

        elif operation == CRUDOperation.READ:
            # result = db[entity].read_by_id(record_id)
            return json.dumps({"status": "success", "operation": "read", "entity": entity, "id": record_id})

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
def generate_custom_id(title_prefix: str = "segmentSource", hash_length: int = 11) -> str:
    """
    Generates a structured ID combining a title prefix, a unique alphanumeric hash, 
    and the current date formatted as MMDDYYYY.
    
    Example output: segmentSource_123e12jen1k_08272026
    """
    # 1. Generate a URL-safe unique token of requested length (UUID fallback included)
    unique_hash = secrets.token_urlsafe(16).replace('-', '').replace('_', '')[:hash_length].lower()
    
    # 2. Format current date as MMDDYYYY
    date_str = datetime.now().strftime("%m%d%Y")
    
    # 3. Combine into final pattern
    return f"{title_prefix}_{unique_hash}_{date_str}"

# LangChain / AI Agent Compatible Tool Wrapper
def generate_id_tool(prefix: str = "segmentSource") -> str:
    """
    Tool signature for LLM agents.
    
    Args:
        prefix: The base name or title for the ID (e.g., 'segmentSource', 'userProfile')
        
    Returns:
        Formatted unique ID string.
    """
    return generate_custom_id(title_prefix=prefix)

