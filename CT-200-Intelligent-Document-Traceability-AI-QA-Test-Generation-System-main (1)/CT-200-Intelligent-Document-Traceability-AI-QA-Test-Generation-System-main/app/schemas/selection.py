from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Dict, Any, Optional

class SelectionCreate(BaseModel):
    selection_name: str
    document_id: str
    version_id: str
    node_ids: List[str]

class NodeSnapshot(BaseModel):
    node_id: str
    logical_node_id: str
    section_number: Optional[str] = None
    heading: str
    level: int
    path: str
    content_hash: str
    body_text: str
    page_start: int
    page_end: int

class SelectionResponse(BaseModel):
    id: str
    selection_name: str
    document_id: str
    version_id: str
    created_at: datetime
    node_ids: List[str]
    logical_node_ids: List[str]
    source_snapshots: Dict[str, Any]
    model_config = ConfigDict(from_attributes=True)
