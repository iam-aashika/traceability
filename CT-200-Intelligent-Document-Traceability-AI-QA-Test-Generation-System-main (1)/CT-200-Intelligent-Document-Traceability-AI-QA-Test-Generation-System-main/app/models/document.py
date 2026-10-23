import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.version_number")
    sections = relationship("SectionNode", back_populates="document", cascade="all, delete-orphan")
    selections = relationship("Selection", back_populates="document", cascade="all, delete-orphan")
