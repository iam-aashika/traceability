from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any

class SectionChildBrief(BaseModel):
    id: str
    logical_node_id: str
    section_number: Optional[str] = None
    heading: str
    level: int
    content_hash: str
    model_config = ConfigDict(from_attributes=True)

class SectionNodeResponse(BaseModel):
    id: str
    logical_node_id: str
    document_id: str
    version_id: str
    section_number: Optional[str] = None
    heading: str
    level: int
    parent_id: Optional[str] = None
    order_index: int
    path: str
    body_text: str
    full_text: str
    content_hash: str
    page_start: int
    page_end: int
    has_table: bool = False
    table_data: Optional[Any] = None
    extraction_confidence: float = 1.0
    extraction_warnings: List[str] = []
    children: List[SectionChildBrief] = []
    model_config = ConfigDict(from_attributes=True)

class SectionSearchResponse(BaseModel):
    id: str
    logical_node_id: str
    document_id: str
    version_id: str
    section_number: Optional[str] = None
    heading: str
    level: int
    path: str
    snippet: str
    content_hash: str
    page_start: int

class DiffSummary(BaseModel):
    old_version: str
    current_version: str
    old_hash: str
    current_hash: str
    diff_text: str
    added_lines: List[str] = []
    removed_lines: List[str] = []

class SectionChangeResponse(BaseModel):
    node_id: str
    logical_node_id: str
    document_id: str
    version_id: str
    status: str  # UNCHANGED, MODIFIED, ADDED, REMOVED, MOVED, REVIEW_REQUIRED
    has_changed: bool
    details: str
    diff_summary: Optional[DiffSummary] = None
