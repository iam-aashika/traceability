import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.document import Document
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.services.pdf_extractor import PDFExtractor
from app.services.hierarchy_builder import HierarchyBuilder
from app.services.hash_service import HashService
from app.schemas.document import DocumentVersionResponse

router = APIRouter(prefix="/api/documents", tags=["Ingestion"])

@router.post("/ingest", response_model=DocumentVersionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    document_id: Optional[str] = Form(None),
    version_label: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Ingest a PDF manual as a new version of a document.
    Extracts text, hierarchy, tables, calculates SHA-256 content hashes,
    and establishes parent-child relationships.
    """
    if not file and not file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'file' upload or 'file_path' must be provided."
        )

    temp_path = None
    try:
        if file:
            suffix = Path(file.filename).suffix or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                target_file = tmp.name
                temp_path = target_file
                filename = file.filename
        else:
            p = Path(file_path)
            if not p.is_file():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File not found at specified path: {file_path}"
                )
            target_file = str(p)
            filename = p.name

        # Calculate file hash
        file_hash = HashService.calculate_file_hash(target_file)

        # Extract document structure
        doc_title, raw_sections, warnings = PDFExtractor.extract_document(target_file)
        if not raw_sections:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to extract any sections from the provided document."
            )

        # Determine Document Entity
        doc_id = document_id or "doc_ct200"
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            doc = Document(
                id=doc_id,
                title=doc_title,
                description="CardioTrack CT-200 Blood Pressure Monitor Technical Manual"
            )
            db.add(doc)
            db.flush()

        # Determine Version Number
        existing_versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_id)
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )
        next_ver_num = (existing_versions[0].version_number + 1) if existing_versions else 1
        label = version_label or f"v{next_ver_num}.0"
        version_id = f"ver_{doc_id}_v{next_ver_num}"

        # Check if identical version already ingested
        for ev in existing_versions:
            if ev.file_hash == file_hash:
                # Return existing version
                return ev

        # Calculate total pages
        import fitz
        with fitz.open(target_file) as pdf_doc:
            total_pages = len(pdf_doc)

        # Create Version record
        version = DocumentVersion(
            id=version_id,
            document_id=doc_id,
            version_number=next_ver_num,
            version_label=label,
            filename=filename,
            file_hash=file_hash,
            total_pages=total_pages
        )
        db.add(version)
        db.flush()

        # Build Hierarchy and instantiate SectionNode records
        nodes = HierarchyBuilder.build_hierarchy(
            document_id=doc_id,
            version_id=version_id,
            raw_sections=raw_sections
        )

        for node in nodes:
            db.add(node)

        db.commit()
        db.refresh(version)

        return version

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
