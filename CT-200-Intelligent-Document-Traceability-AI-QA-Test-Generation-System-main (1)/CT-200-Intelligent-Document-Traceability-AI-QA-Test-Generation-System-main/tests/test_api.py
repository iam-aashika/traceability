import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine, SessionLocal
from app.services.storage_service import doc_store

@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c

def test_api_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_api_end_to_end_flow(client):
    import uuid
    doc_id = f"doc_test_{uuid.uuid4().hex[:8]}"

    # 1. Ingest v1
    resp_ingest_v1 = client.post(
        "/api/documents/ingest",
        data={
            "file_path": "data/ct200_manual_v1.pdf",
            "document_id": doc_id,
            "version_label": "v1.0"
        }
    )
    assert resp_ingest_v1.status_code == 201
    v1_data = resp_ingest_v1.json()
    assert v1_data["version_label"] == "v1.0"
    v1_id = v1_data["id"]

    # 2. Browse sections
    resp_sections = client.get(f"/api/documents/{doc_id}/sections?version_id={v1_id}")
    assert resp_sections.status_code == 200
    sections = resp_sections.json()
    assert len(sections) > 0

    # 3. Search sections
    resp_search = client.get(f"/api/sections/search?q=inflation&document_id={doc_id}")
    assert resp_search.status_code == 200
    search_hits = resp_search.json()
    assert len(search_hits) > 0

    # 4. Lookup specific node: 3.2 Cuff Inflation Sequence
    target_node_id = f"{v1_id}_sec_3_2_cuff_inflation_sequence"
    resp_node = client.get(f"/api/sections/{target_node_id}")
    assert resp_node.status_code == 200
    node_data = resp_node.json()
    assert node_data["heading"] == "Cuff Inflation Sequence"
    assert "40 mmHg" in node_data["body_text"]

    # 5. Create version-pinned selection
    resp_sel = client.post(
        "/api/selections",
        json={
            "selection_name": "Safety and Inflation Requirements",
            "document_id": doc_id,
            "version_id": v1_id,
            "node_ids": [target_node_id]
        }
    )
    assert resp_sel.status_code == 201
    selection_id = resp_sel.json()["id"]

    # 6. Generate test cases
    resp_gen = client.post(f"/api/generations/{selection_id}")
    assert resp_gen.status_code == 201
    gen_data = resp_gen.json()
    assert gen_data["was_cached"] is False
    assert 3 <= len(gen_data["test_cases"]) <= 5
    gen_id = gen_data["generation_id"]

    # Verify duplicate caching policy
    resp_gen_cached = client.post(f"/api/generations/{selection_id}")
    assert resp_gen_cached.status_code == 201
    assert resp_gen_cached.json()["was_cached"] is True
    assert resp_gen_cached.json()["generation_id"] == gen_id

    # 7. Retrieve generation before v2 -> Should be CURRENT
    resp_retrieval_v1 = client.get(f"/api/generations/{gen_id}")
    assert resp_retrieval_v1.status_code == 200
    ret_v1_data = resp_retrieval_v1.json()
    assert ret_v1_data["overall_staleness_status"] == "CURRENT"

    # 8. Ingest v2
    resp_ingest_v2 = client.post(
        "/api/documents/ingest",
        data={
            "file_path": "data/ct200_manual_v2.pdf",
            "document_id": doc_id,
            "version_label": "v2.0"
        }
    )
    assert resp_ingest_v2.status_code == 201
    assert resp_ingest_v2.json()["version_label"] == "v2.0"

    # 9. Check section changes across versions
    resp_changes = client.get(f"/api/sections/{target_node_id}/changes")
    assert resp_changes.status_code == 200
    changes_data = resp_changes.json()
    assert changes_data["status"] == "MODIFIED"
    assert changes_data["has_changed"] is True
    assert changes_data["diff_summary"] is not None

    # 10. Retrieve historical generation again -> Should now be flagged STALE!
    resp_retrieval_v2 = client.get(f"/api/generations/{gen_id}")
    assert resp_retrieval_v2.status_code == 200
    ret_v2_data = resp_retrieval_v2.json()
    assert ret_v2_data["overall_staleness_status"] == "STALE"
    assert ret_v2_data["has_stale_requirements"] is True
    assert ret_v2_data["node_staleness_details"][0]["change_category"] == "NUMERICAL_THRESHOLD"
    assert "High-priority" in ret_v2_data["node_staleness_details"][0]["human_review_recommendation"]

    # 11. Test retrieval by selection ID and node ID
    resp_by_sel = client.get(f"/api/generations/by-selection/{selection_id}")
    assert resp_by_sel.status_code == 200
    assert len(resp_by_sel.json()) >= 1

    resp_by_node = client.get(f"/api/generations/by-node/{target_node_id}")
    assert resp_by_node.status_code == 200
    assert len(resp_by_node.json()) >= 1
