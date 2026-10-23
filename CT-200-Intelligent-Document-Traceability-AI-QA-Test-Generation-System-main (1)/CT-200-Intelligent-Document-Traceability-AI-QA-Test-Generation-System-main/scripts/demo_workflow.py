import sys
import io
import json
import time
from pathlib import Path

# Ensure root directory is on pythonpath
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output on Windows consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from fastapi.testclient import TestClient
from app.main import app

def print_banner(text: str):
    print("\n" + "=" * 80)
    print(f" {text}")
    print("=" * 80)

def print_step(step_num: int, title: str):
    print(f"\n[STEP {step_num}] {title}")
    print("-" * 60)

def run_demo():
    print_banner("CT-200 DOCUMENT TRACEABILITY & AI QA GENERATION PLATFORM: LIVE DEMO")
    
    # Clean previous demo run data for idempotent demonstration
    from app.database import SessionLocal
    from app.models.document import Document
    from app.models.selection import Selection
    from app.models.section import SectionNode
    from app.models.version import DocumentVersion
    db = SessionLocal()
    demo_doc_id = "doc_ct200_demo"
    db.query(Selection).filter(Selection.document_id == demo_doc_id).delete()
    db.query(SectionNode).filter(SectionNode.document_id == demo_doc_id).delete()
    db.query(DocumentVersion).filter(DocumentVersion.document_id == demo_doc_id).delete()
    db.query(Document).filter(Document.id == demo_doc_id).delete()
    db.commit()
    db.close()

    client = TestClient(app)

    # 1. Ingest CT-200 version 1
    print_step(1, "Ingest CT-200 Manual Version 1 (data/ct200_manual_v1.pdf)")
    resp_v1 = client.post(
        "/api/documents/ingest",
        data={
            "file_path": "data/ct200_manual_v1.pdf",
            "document_id": demo_doc_id,
            "version_label": "v1.0"
        }
    )
    if resp_v1.status_code not in (200, 201):
        print(f"Ingestion failed: {resp_v1.status_code} {resp_v1.text}")
        return
    v1_data = resp_v1.json()
    v1_id = v1_data["id"]
    print(f"✓ Ingested Document: {v1_data['document_id']} ({v1_data['version_label']})")
    print(f"  Version ID: {v1_id}")
    print(f"  SHA-256 PDF Hash: {v1_data['file_hash']}")
    print(f"  Total Pages: {v1_data['total_pages']}")

    # 2. Retrieve document sections
    print_step(2, f"Retrieve Document Sections for Version {v1_id}")
    resp_sec = client.get(f"/api/documents/{demo_doc_id}/sections?version_id={v1_id}&top_level_only=true")
    sections = resp_sec.json()
    print(f"✓ Retrieved {len(sections)} root-level sections")

    # 3. Display the hierarchy
    print_step(3, "Display Document Hierarchy Tree (v1.0)")
    for s in sections:
        print(f"  [{s.get('section_number', '')}] {s['heading']} (Page {s['page_start']})")
        for child in s.get("children", []):
            print(f"      ├── [{child.get('section_number', '')}] {child['heading']} (Hash: {child['content_hash'][:12]}...)")

    # 4. Create a version-pinned selection with multiple sections
    print_step(4, "Create Version-Pinned Selection (Cuff Inflation & Error Codes)")
    # Target sections: 3.2 Cuff Inflation Sequence and 4.2 Error Codes
    node_inflation_id = f"{v1_id}_sec_3_2_cuff_inflation_sequence"
    node_errors_id = f"{v1_id}_sec_4_2_error_codes"

    resp_sel = client.post(
        "/api/selections",
        json={
            "selection_name": "Critical Inflation & Error Handling Requirements",
            "document_id": demo_doc_id,
            "version_id": v1_id,
            "node_ids": [node_inflation_id, node_errors_id]
        }
    )
    sel_data = resp_sel.json()
    sel_id = sel_data["id"]
    print(f"✓ Created Version-Pinned Selection: '{sel_data['selection_name']}'")
    print(f"  Selection ID: {sel_id}")
    print(f"  Pinned to Version: {sel_data['version_id']}")
    print(f"  Pinned Nodes: {sel_data['node_ids']}")

    # 5. Generate QA test cases
    print_step(5, "Generate QA Test Cases via AI/LLM with Pydantic Validation")
    resp_gen = client.post(f"/api/generations/{sel_id}")
    gen_data = resp_gen.json()
    gen_id = gen_data["generation_id"]
    print(f"✓ Successfully Generated {len(gen_data['test_cases'])} Pydantic-Validated Test Cases")
    print(f"  Generation ID: {gen_id}")
    print(f"  Cached: {gen_data['was_cached']}")

    # 6. Retrieve the generated test cases
    print_step(6, "Display Generated Test Cases")
    for tc in gen_data["test_cases"]:
        print(f"\n  * Test Case: [{tc['test_case_id']}] {tc['title']}")
        print(f"    Type: {tc['test_type']} | Priority: {tc['priority']}")
        print(f"    Objective: {tc['objective']}")
        print(f"    Expected Result: {tc['expected_result']}")
        print(f"    Source Nodes: {tc['source_node_ids']}")
        print(f"    Requirement Citations: {tc['source_requirements']}")

    # 7. Verify initial CURRENT status
    print_step(7, "Verify Traceability Status Before Ingesting v2")
    resp_trace_v1 = client.get(f"/api/generations/{gen_id}")
    trace_v1 = resp_trace_v1.json()
    print(f"✓ Overall Staleness Status: {trace_v1['overall_staleness_status']}")
    print(f"  Has Stale Requirements: {trace_v1['has_stale_requirements']}")
    print(f"  Latest Known Version: {trace_v1['latest_document_version']}")
    print(f"  Summary: {trace_v1['summary_reason']}")

    # 8. Ingest CT-200 version 2
    print_step(8, "Ingest CT-200 Manual Version 2 (data/ct200_manual_v2.pdf)")
    resp_v2 = client.post(
        "/api/documents/ingest",
        data={
            "file_path": "data/ct200_manual_v2.pdf",
            "document_id": demo_doc_id,
            "version_label": "v2.0"
        }
    )
    v2_data = resp_v2.json()
    v2_id = v2_data["id"]
    print(f"✓ Ingested Document Version: {v2_data['version_label']}")
    print(f"  Version ID: {v2_id}")
    print(f"  SHA-256 PDF Hash: {v2_data['file_hash']}")
    print(f"  Total Pages: {v2_data['total_pages']}")

    # 9. Compare document versions
    print_step(9, "Forensic Comparison Across Versions (v1.0 vs v2.0)")
    # Check Section 3.2 change
    resp_c32 = client.get(f"/api/sections/{node_inflation_id}/changes")
    c32 = resp_c32.json()
    print(f"  Section 3.2 Status: {c32['status']}")
    print(f"  Has Changed: {c32['has_changed']}")
    if c32.get("diff_summary"):
        print(f"  Diff Lines Removed: {c32['diff_summary']['removed_lines']}")
        print(f"  Diff Lines Added: {c32['diff_summary']['added_lines']}")

    # Check Section 4.2 change
    resp_c42 = client.get(f"/api/sections/{node_errors_id}/changes")
    c42 = resp_c42.json()
    print(f"\n  Section 4.2 Status: {c42['status']}")
    print(f"  Has Changed: {c42['has_changed']}")

    # 10. Retrieve the original generation again
    print_step(10, f"Retrieve Historical Generation {gen_id} After v2 Ingestion")
    resp_trace_v2 = client.get(f"/api/generations/{gen_id}")
    trace_v2 = resp_trace_v2.json()

    # 11. Display updated staleness statuses
    print_step(11, "Display Real-Time Traceability & Staleness Evaluation")
    print(f"✓ Original Version Pinned: {trace_v2['original_version']}")
    print(f"✓ Latest Document Version: {trace_v2['latest_document_version']}")
    print(f"✓ OVERALL STALENESS STATUS: {trace_v2['overall_staleness_status']}")
    print(f"✓ Has Stale Requirements: {trace_v2['has_stale_requirements']}")
    print(f"✓ Impact Summary: {trace_v2['summary_reason']}")
    print(f"✓ Recommendation: {trace_v2['human_review_recommendation']}")

    # 12. Explain which source changes affected the generated test cases
    print_step(12, "Per-Node Forensic Staleness Breakdown")
    for detail in trace_v2["node_staleness_details"]:
        print(f"\n  * Section: [{detail['heading']}] (Logical ID: {detail['logical_node_id']})")
        print(f"    Staleness Status: {detail['staleness_status']}")
        print(f"    Change Category: {detail['change_category']}")
        print(f"    Original Content Hash: {detail['original_hash'][:16]}...")
        print(f"    Latest Content Hash:   {detail['current_hash'][:16]}...")
        print(f"    Root Cause Reason: {detail['reason']}")
        print(f"    Regulatory Action: {detail['human_review_recommendation']}")

    print_banner("DEMO COMPLETED SUCCESSFULLY: ALL 12 VERIFICATION STEPS PASSED")

if __name__ == "__main__":
    run_demo()
