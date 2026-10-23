import pytest
from app.services.staleness_service import StalenessService
from app.models.version import DocumentVersion
from app.models.section import SectionNode
from app.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def mock_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Create v1 and v2 document versions
    v1 = DocumentVersion(
        id="ver_doc1_v1",
        document_id="doc1",
        version_number=1,
        version_label="v1.0",
        filename="manual_v1.pdf",
        file_hash="hash_pdf_v1"
    )
    v2 = DocumentVersion(
        id="ver_doc1_v2",
        document_id="doc1",
        version_number=2,
        version_label="v2.0",
        filename="manual_v2.pdf",
        file_hash="hash_pdf_v2"
    )
    db.add(v1)
    db.add(v2)
    db.flush()

    # Section 3.2 in v2 (with numerical change: 30 mmHg instead of 40 mmHg)
    node_v2_3_2 = SectionNode(
        id="ver_doc1_v2_sec_3_2",
        logical_node_id="sec_3_2_cuff_inflation",
        document_id="doc1",
        version_id="ver_doc1_v2",
        section_number="3.2",
        heading="Cuff Inflation Sequence",
        level=2,
        path="/3/3.2",
        body_text="Device inflates in 30 mmHg increments up to a maximum of 299 mmHg.",
        full_text="Cuff Inflation Sequence\n\nDevice inflates in 30 mmHg increments up to a maximum of 299 mmHg.",
        content_hash="hash_v2_3_2",
        page_start=3,
        page_end=3
    )

    # Section 1.1 in v2 (identical text)
    node_v2_1_1 = SectionNode(
        id="ver_doc1_v2_sec_1_1",
        logical_node_id="sec_1_1_intended_use",
        document_id="doc1",
        version_id="ver_doc1_v2",
        section_number="1.1",
        heading="Intended Use",
        level=2,
        path="/1/1.1",
        body_text="Intended for adults with arm circumference 22-42 cm.",
        full_text="Intended Use\n\nIntended for adults with arm circumference 22-42 cm.",
        content_hash="hash_v1_1_1",
        page_start=1,
        page_end=1
    )

    # Section with subtle wording change
    node_v2_wording = SectionNode(
        id="ver_doc1_v2_sec_wording",
        logical_node_id="sec_wording_change",
        document_id="doc1",
        version_id="ver_doc1_v2",
        section_number="6.1",
        heading="Cleaning Instructions",
        level=2,
        path="/6/6.1",
        body_text="Wipe the device housing and cuff exterior with a soft dry cloth.",
        full_text="Cleaning Instructions\n\nWipe the device housing and cuff exterior with a soft dry cloth.",
        content_hash="hash_v2_wording",
        page_start=5,
        page_end=5
    )

    db.add(node_v2_3_2)
    db.add(node_v2_1_1)
    db.add(node_v2_wording)
    db.commit()

    yield db
    db.close()

def test_staleness_numerical_threshold_change(mock_db):
    # Old requirement had 40 mmHg
    detail = StalenessService.evaluate_node_staleness(
        db=mock_db,
        document_id="doc1",
        original_version_id="ver_doc1_v1",
        node_id="ver_doc1_v1_sec_3_2",
        logical_node_id="sec_3_2_cuff_inflation",
        original_heading="Cuff Inflation Sequence",
        original_text="Device inflates in 40 mmHg increments up to a maximum of 299 mmHg.",
        original_hash="hash_v1_3_2_old"
    )
    assert detail.staleness_status == "STALE"
    assert detail.change_category == "NUMERICAL_THRESHOLD"
    assert "Numerical limits or timing changed" in detail.reason
    assert "High-priority" in detail.human_review_recommendation

def test_staleness_unchanged_content(mock_db):
    detail = StalenessService.evaluate_node_staleness(
        db=mock_db,
        document_id="doc1",
        original_version_id="ver_doc1_v1",
        node_id="ver_doc1_v1_sec_1_1",
        logical_node_id="sec_1_1_intended_use",
        original_heading="Intended Use",
        original_text="Intended for adults with arm circumference 22-42 cm.",
        original_hash="hash_v1_1_1"
    )
    assert detail.staleness_status == "CURRENT"
    assert detail.change_category == "NONE"

def test_staleness_wording_change_requires_review(mock_db):
    # Old wording was "device body" instead of "device housing", no numbers changed
    detail = StalenessService.evaluate_node_staleness(
        db=mock_db,
        document_id="doc1",
        original_version_id="ver_doc1_v1",
        node_id="ver_doc1_v1_sec_wording",
        logical_node_id="sec_wording_change",
        original_heading="Cleaning Instructions",
        original_text="Wipe the device body and cuff exterior with a soft dry cloth.",
        original_hash="hash_v1_wording_old"
    )
    assert detail.staleness_status == "REVIEW_REQUIRED"
    assert detail.change_category == "TEXT_MODIFIED"
    assert "Manual QA inspection recommended" in detail.human_review_recommendation

def test_staleness_source_removed(mock_db):
    detail = StalenessService.evaluate_node_staleness(
        db=mock_db,
        document_id="doc1",
        original_version_id="ver_doc1_v1",
        node_id="ver_doc1_v1_sec_deprecated",
        logical_node_id="sec_deprecated_section",
        original_heading="Deprecated Section",
        original_text="Some old requirement",
        original_hash="hash_old"
    )
    assert detail.staleness_status == "SOURCE_REMOVED"
    assert detail.change_category == "DELETED"
