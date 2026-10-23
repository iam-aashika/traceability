import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False, default=1)
    version_label = Column(String, nullable=False)  # e.g., "v1.0", "v2.0"
    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False)  # SHA-256 of the raw PDF
    total_pages = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    document = relationship("Document", back_populates="versions")
    sections = relationship("SectionNode", back_populates="version", cascade="all, delete-orphan", order_by="SectionNode.order_index")
    selections = relationship("Selection", back_populates="version", cascade="all, delete-orphan")
