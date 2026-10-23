from sqlalchemy import Column, String, Integer, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class SectionNode(Base):
    __tablename__ = "sections"

    id = Column(String, primary_key=True, index=True)  # e.g., "node_ct200_v1_3_2"
    logical_node_id = Column(String, nullable=False, index=True)  # stable logical ID across versions
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    version_id = Column(String, ForeignKey("document_versions.id"), nullable=False, index=True)
    
    section_number = Column(String, nullable=True)  # "1", "1.1", "3.2", etc.
    heading = Column(String, nullable=False, index=True)
    level = Column(Integer, nullable=False, default=1)  # 1 for root section, 2 for subsection, etc.
    parent_id = Column(String, ForeignKey("sections.id"), nullable=True, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    path = Column(String, nullable=False)  # e.g., "/1/1.1" or hierarchy path
    
    body_text = Column(Text, nullable=False, default="")
    full_text = Column(Text, nullable=False, default="")
    content_hash = Column(String, nullable=False, index=True)  # SHA-256
    
    page_start = Column(Integer, nullable=False, default=1)
    page_end = Column(Integer, nullable=False, default=1)
    
    has_table = Column(Boolean, default=False)
    table_data = Column(Text, nullable=True)  # JSON-encoded table rows
    
    extraction_confidence = Column(Float, default=1.0)
    extraction_warnings = Column(Text, default="[]")  # JSON-encoded list of warning strings

    # Relationships
    document = relationship("Document", back_populates="sections")
    version = relationship("DocumentVersion", back_populates="sections")
    parent = relationship("SectionNode", remote_side=[id], backref="children")
