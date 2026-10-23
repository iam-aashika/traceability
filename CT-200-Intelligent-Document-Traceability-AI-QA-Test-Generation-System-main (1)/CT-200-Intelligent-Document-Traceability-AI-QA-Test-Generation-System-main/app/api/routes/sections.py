import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models.section import SectionNode
from app.schemas.section import (
    SectionNodeResponse,
    SectionChildBrief,
    SectionSearchResponse,
    SectionChangeResponse
)
from app.services.version_service import VersionService

router = APIRouter(prefix="/api/sections", tags=["Sections"])

@router.get("/search", response_model=List[SectionSearchResponse])
def search_sections(
    q: str = Query(..., min_length=2, description="Search term for heading or body text"),
    document_id: Optional[str] = Query(None, description="Filter by document ID"),
    version_id: Optional[str] = Query(None, description="Filter by version ID"),
    db: Session = Depends(get_db)
):
    """Search sections by heading or body text."""
    query = db.query(SectionNode)
    if document_id:
        query = query.filter(SectionNode.document_id == document_id)
    if version_id:
        query = query.filter(SectionNode.version_id == version_id)

    search_filter = or_(
        SectionNode.heading.ilike(f"%{q}%"),
        SectionNode.body_text.ilike(f"%{q}%")
    )
    results = query.filter(search_filter).limit(50).all()

    search_responses = []
    for node in results:
        # Create snippet
        text = node.body_text or node.heading
        lower_text = text.lower()
        idx = lower_text.find(q.lower())
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(q) + 60)
            snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
        else:
            snippet = text[:100] + ("..." if len(text) > 100 else "")

        search_responses.append(SectionSearchResponse(
            id=node.id,
            logical_node_id=node.logical_node_id,
            document_id=node.document_id,
            version_id=node.version_id,
            section_number=node.section_number,
            heading=node.heading,
            level=node.level,
            path=node.path,
            snippet=snippet,
            content_hash=node.content_hash,
            page_start=node.page_start
        ))

    return search_responses

@router.get("/{node_id}", response_model=SectionNodeResponse)
def get_section(node_id: str, db: Session = Depends(get_db)):
    """
    Get detailed section information including parent, children, full text, and content hash.
    """
    node = db.query(SectionNode).filter(SectionNode.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section node '{node_id}' not found."
        )

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

    return SectionNodeResponse(
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
    )

@router.get("/{node_id}/changes", response_model=SectionChangeResponse)
def get_section_changes(node_id: str, db: Session = Depends(get_db)):
    """
    Given a node ID, determine whether it has changed across versions,
    and return its status and lightweight diff summary.
    """
    try:
        result = VersionService.compare_node_across_versions(db, node_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
