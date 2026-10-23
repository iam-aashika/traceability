import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.models.selection import Selection
from app.schemas.selection import SelectionCreate, SelectionResponse

router = APIRouter(prefix="/api/selections", tags=["Selections"])

@router.post("", response_model=SelectionResponse, status_code=status.HTTP_201_CREATED)
def create_selection(payload: SelectionCreate, db: Session = Depends(get_db)):
    """
    Create a version-pinned selection of document section nodes.
    Captures immutable snapshots of the exact node content, headings,
    and content hashes at creation time.
    """
    # Validate version exists
    version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.id == payload.version_id,
            DocumentVersion.document_id == payload.document_id
        )
        .first()
    )
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{payload.version_id}' for document '{payload.document_id}' not found."
        )

    if not payload.node_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one node_id must be provided in the selection."
        )

    # Fetch and validate all nodes belong to specified version
    nodes = (
        db.query(SectionNode)
        .filter(
            SectionNode.id.in_(payload.node_ids),
            SectionNode.version_id == payload.version_id
        )
        .all()
    )

    found_node_ids = {n.id for n in nodes}
    missing_nodes = set(payload.node_ids) - found_node_ids
    if missing_nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Selected nodes {list(missing_nodes)} do not exist or do not belong to "
                f"version '{payload.version_id}'."
            )
        )

    # Build frozen snapshots
    source_snapshots = {}
    logical_ids = []
    for node in nodes:
        logical_ids.append(node.logical_node_id)
        source_snapshots[node.id] = {
            "node_id": node.id,
            "logical_node_id": node.logical_node_id,
            "section_number": node.section_number,
            "heading": node.heading,
            "level": node.level,
            "path": node.path,
            "content_hash": node.content_hash,
            "body_text": node.body_text,
            "page_start": node.page_start,
            "page_end": node.page_end
        }

    selection_id = f"sel_{uuid.uuid4().hex[:12]}"
    selection = Selection(
        id=selection_id,
        selection_name=payload.selection_name,
        document_id=payload.document_id,
        version_id=payload.version_id,
        node_ids=json.dumps(payload.node_ids),
        logical_node_ids=json.dumps(logical_ids),
        source_snapshots=json.dumps(source_snapshots)
    )

    db.add(selection)
    db.commit()
    db.refresh(selection)

    return SelectionResponse(
        id=selection.id,
        selection_name=selection.selection_name,
        document_id=selection.document_id,
        version_id=selection.version_id,
        created_at=selection.created_at,
        node_ids=payload.node_ids,
        logical_node_ids=logical_ids,
        source_snapshots=source_snapshots
    )

@router.get("/{selection_id}", response_model=SelectionResponse)
def get_selection(selection_id: str, db: Session = Depends(get_db)):
    """
    Retrieve a version-pinned selection and its immutable source snapshot.
    """
    sel = db.query(Selection).filter(Selection.id == selection_id).first()
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection '{selection_id}' not found."
        )

    return SelectionResponse(
        id=sel.id,
        selection_name=sel.selection_name,
        document_id=sel.document_id,
        version_id=sel.version_id,
        created_at=sel.created_at,
        node_ids=json.loads(sel.node_ids),
        logical_node_ids=json.loads(sel.logical_node_ids),
        source_snapshots=json.loads(sel.source_snapshots)
    )
