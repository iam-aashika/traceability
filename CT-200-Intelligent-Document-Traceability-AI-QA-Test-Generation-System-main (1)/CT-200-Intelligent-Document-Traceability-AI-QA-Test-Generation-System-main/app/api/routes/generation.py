import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.selection import Selection
from app.models.version import DocumentVersion
from app.services.llm_service import LLMService
from app.services.storage_service import doc_store
from app.schemas.generation import GenerationResponse, TestCase
from app.config import settings

router = APIRouter(prefix="/api/generations", tags=["Test Generation"])

@router.post("/{selection_id}", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
def generate_qa_test_cases(
    selection_id: str,
    force_regenerate: bool = Query(False, description="Force new generation even if one exists for this selection"),
    db: Session = Depends(get_db)
):
    """
    Generate 3 to 5 validated QA test cases from a version-pinned selection.
    
    Duplicate Policy:
    - If force_regenerate is False and a successful generation already exists
      for this selection_id, reuse the existing generation (was_cached=True).
    - If force_regenerate is True, create an independent new generation without
      destroying historical records.
    """
    sel = db.query(Selection).filter(Selection.id == selection_id).first()
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection '{selection_id}' not found."
        )

    # Check duplicate policy
    if not force_regenerate:
        existing = doc_store.get_by_selection_id(selection_id)
        if existing:
            latest_existing = existing[-1]
            return GenerationResponse(
                generation_id=latest_existing["generation_id"],
                selection_id=latest_existing["selection_id"],
                selection_name=latest_existing.get("selection_name", sel.selection_name),
                document_id=latest_existing["document_id"],
                version_id=latest_existing["version_id"],
                version_label=latest_existing.get("version_label", "v1.0"),
                created_at=datetime.fromisoformat(latest_existing["created_at"]) if isinstance(latest_existing["created_at"], str) else latest_existing["created_at"],
                llm_provider=latest_existing["llm_provider"],
                model_name=latest_existing["model_name"],
                prompt_version=latest_existing.get("prompt_version", "v1.0"),
                source_node_ids=latest_existing["source_node_ids"],
                logical_node_ids=latest_existing["logical_node_ids"],
                source_content_hashes=latest_existing["source_content_hashes"],
                test_cases=[TestCase.model_validate(tc) for tc in latest_existing["test_cases"]],
                was_cached=True
            )

    # Fetch version details for metadata
    ver = db.query(DocumentVersion).filter(DocumentVersion.id == sel.version_id).first()
    version_label = ver.version_label if ver else "v1.0"

    snapshots = json.loads(sel.source_snapshots)
    logical_ids = json.loads(sel.logical_node_ids)
    node_ids = json.loads(sel.node_ids)
    source_hashes = {nid: data["content_hash"] for nid, data in snapshots.items()}

    try:
        test_cases = LLMService.generate_test_cases(snapshots)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"QA Test Generation failed Pydantic validation: {str(err)}"
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM Provider error: {str(err)}"
        )

    generation_id = f"gen_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    record = {
        "generation_id": generation_id,
        "selection_id": sel.id,
        "selection_name": sel.selection_name,
        "document_id": sel.document_id,
        "version_id": sel.version_id,
        "version_label": version_label,
        "created_at": now.isoformat(),
        "llm_provider": settings.LLM_PROVIDER,
        "model_name": settings.LLM_MODEL,
        "prompt_version": "v1.0",
        "source_node_ids": node_ids,
        "logical_node_ids": logical_ids,
        "source_content_hashes": source_hashes,
        "source_snapshots": snapshots,
        "test_cases": [tc.model_dump() for tc in test_cases]
    }

    doc_store.save_generation(record)

    return GenerationResponse(
        generation_id=generation_id,
        selection_id=sel.id,
        selection_name=sel.selection_name,
        document_id=sel.document_id,
        version_id=sel.version_id,
        version_label=version_label,
        created_at=now,
        llm_provider=settings.LLM_PROVIDER,
        model_name=settings.LLM_MODEL,
        prompt_version="v1.0",
        source_node_ids=node_ids,
        logical_node_ids=logical_ids,
        source_content_hashes=source_hashes,
        test_cases=test_cases,
        was_cached=False
    )
