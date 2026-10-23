from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional

class DocumentBase(BaseModel):
    title: str
    description: Optional[str] = None

class DocumentCreate(DocumentBase):
    id: Optional[str] = None

class DocumentVersionResponse(BaseModel):
    id: str
    document_id: str
    version_number: int
    version_label: str
    filename: str
    file_hash: str
    total_pages: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class DocumentResponse(DocumentBase):
    id: str
    created_at: datetime
    updated_at: datetime
    versions: List[DocumentVersionResponse] = []
    model_config = ConfigDict(from_attributes=True)
