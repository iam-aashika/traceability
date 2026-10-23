import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.document import Document
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.schemas.document import DocumentResponse, DocumentVersionResponse
from app.schemas.section import SectionNodeResponse, SectionChildBrief

router = APIRouter(prefix="/api/documents", tags=["Documents"])

@router.get("", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    """List all documents currently in the system."""
    docs = db.query(Document).all()
    return docs

@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Get document details by ID."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")
    return doc

@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
def list_document_versions(document_id: str, db: Session = Depends(get_db)):
    """List all ingested versions for a specific document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")
    return doc.versions

@router.get("/{document_id}/sections", response_model=List[SectionNodeResponse])
def list_document_sections(
    document_id: str,
    version_id: Optional[str] = Query(None, description="Target version ID (defaults to latest)"),
    version: Optional[str] = Query(None, description="Version label (e.g. 'v1', 'v2') or version ID — alias for version_id"),
    top_level_only: bool = Query(True, description="Return only top-level (level=1) sections"),
    db: Session = Depends(get_db)
):
    """
    List sections for a document version (defaults to latest version).
    Returns top-level sections with children briefs attached.
    Use `version_id` (exact ID) or `version` (label like 'v1' or 'v2').
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found.")

    # Resolve version: prefer version_id; fall back to version (label or id)
    resolved_version_id = version_id or version

    if resolved_version_id:
        # Try direct ID match first
        target_version = db.query(DocumentVersion).filter(
            DocumentVersion.id == resolved_version_id,
            DocumentVersion.document_id == document_id
        ).first()
        # If not found, try label match
        if not target_version:
            target_version = db.query(DocumentVersion).filter(
                DocumentVersion.version_label == resolved_version_id,
                DocumentVersion.document_id == document_id
            ).first()
        if not target_version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version '{resolved_version_id}' not found for document '{document_id}'.")
    else:
        # Default to latest version
        target_version = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        if not target_version:
            return []

    query = db.query(SectionNode).filter(SectionNode.version_id == target_version.id)
    if top_level_only:
        query = query.filter(SectionNode.level == 1)

    nodes = query.order_index_asc().all() if hasattr(query, "order_index_asc") else query.order_by(SectionNode.order_index).all()

    # Build response with parsed table data & warnings
    responses = []
    for node in nodes:
        children_briefs = [
            SectionChildBrief(
                id=c.id,
                logical_node_id=c.logical_node_id,
                section_number=c.section_number,
                heading=c.heading,
                level=c.level,
                content_hash=c.content_hash
            )
            for c in node.children
        ]
        
        parsed_table = json.loads(node.table_data) if node.table_data else None
        parsed_warnings = json.loads(node.extraction_warnings) if node.extraction_warnings else []

        responses.append(SectionNodeResponse(
            id=node.id,
            logical_node_id=node.logical_node_id,
            document_id=node.document_id,
            version_id=node.version_id,
            section_number=node.section_number,
            heading=node.heading,
            level=node.level,
            parent_id=node.parent_id,
            order_index=node.order_index,
            path=node.path,
            body_text=node.body_text,
            full_text=node.full_text,
            content_hash=node.content_hash,
            page_start=node.page_start,
            page_end=node.page_end,
            has_table=node.has_table,
            table_data=parsed_table,
            extraction_confidence=node.extraction_confidence,
            extraction_warnings=parsed_warnings,
            children=children_briefs
        ))

    return responses
