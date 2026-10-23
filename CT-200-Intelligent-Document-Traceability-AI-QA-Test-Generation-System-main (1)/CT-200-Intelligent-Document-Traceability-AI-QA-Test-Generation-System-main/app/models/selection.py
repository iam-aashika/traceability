import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Selection(Base):
    __tablename__ = "selections"

    id = Column(String, primary_key=True, index=True)
    selection_name = Column(String, nullable=False)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    version_id = Column(String, ForeignKey("document_versions.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    node_ids = Column(Text, nullable=False)  # JSON-encoded list of node IDs
    logical_node_ids = Column(Text, nullable=False)  # JSON-encoded list of logical node IDs
    source_snapshots = Column(Text, nullable=False)  # JSON-encoded mapping of node_id -> snapshot dict

    document = relationship("Document", back_populates="selections")
    version = relationship("DocumentVersion", back_populates="selections")
