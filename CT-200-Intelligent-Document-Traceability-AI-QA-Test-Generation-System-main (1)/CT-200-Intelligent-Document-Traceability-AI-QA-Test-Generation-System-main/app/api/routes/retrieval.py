from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.storage_service import doc_store
from app.services.staleness_service import StalenessService
from app.schemas.generation import TestTraceabilityResponse

router = APIRouter(prefix="/api/generations", tags=["Retrieval & Staleness"])

@router.get("/{generation_id}", response_model=TestTraceabilityResponse)
def get_generation_by_id(generation_id: str, db: Session = Depends(get_db)):
    """
    Retrieve historical generated test cases by generation ID,
    evaluating current staleness against the latest document version in real time.
    """
    doc = doc_store.get_by_id(generation_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation '{generation_id}' not found in storage."
        )

    return StalenessService.evaluate_generation_traceability(db, doc)

@router.get("/by-selection/{selection_id}", response_model=List[TestTraceabilityResponse])
def get_generations_by_selection(selection_id: str, db: Session = Depends(get_db)):
    """
    Retrieve all test case generations associated with a specific selection ID,
    evaluating each for staleness against current document specifications.
    """
    docs = doc_store.get_by_selection_id(selection_id)
    if not docs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generations found for selection '{selection_id}'."
        )

    return [StalenessService.evaluate_generation_traceability(db, d) for d in docs]

@router.get("/by-node/{node_id}", response_model=List[TestTraceabilityResponse])
def get_generations_by_node(node_id: str, db: Session = Depends(get_db)):
    """
    Retrieve all test case generations that trace back to a specific node ID,
    evaluating current staleness against the latest document version.
    """
    docs = doc_store.get_by_node_id(node_id)
    if not docs:
        return []

    return [StalenessService.evaluate_generation_traceability(db, d) for d in docs]
