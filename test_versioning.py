import pytest
from app.services.pdf_extractor import PDFExtractor
from app.services.hierarchy_builder import HierarchyBuilder
from app.services.version_service import VersionService

V1_PATH = "data/ct200_manual_v1.pdf"
V2_PATH = "data/ct200_manual_v2.pdf"

@pytest.fixture(scope="module")
def versions_data():
    _, raw_v1, _ = PDFExtractor.extract_document(V1_PATH)
    nodes_v1 = HierarchyBuilder.build_hierarchy("doc_test", "ver_v1", raw_v1)

    _, raw_v2, _ = PDFExtractor.extract_document(V2_PATH)
    nodes_v2 = HierarchyBuilder.build_hierarchy("doc_test", "ver_v2", raw_v2)

    return nodes_v1, nodes_v2

def test_version_matching_unchanged_sections(versions_data):
    nodes_v1, nodes_v2 = versions_data
    results = VersionService.match_nodes(nodes_v1, nodes_v2)

    # Intended Use (1.1) is identical between v1 and v2
    res_1_1 = [r for r in results if r.old_node and r.old_node.section_number == "1.1"][0]
    assert res_1_1.status == "UNCHANGED"
    assert res_1_1.old_node.content_hash == res_1_1.new_node.content_hash

    # Section 3.1 shifted pages, but text is identical -> UNCHANGED
    res_3_1 = [r for r in results if r.old_node and r.old_node.section_number == "3.1"][0]
    assert res_3_1.status == "UNCHANGED"

def test_version_matching_modified_sections(versions_data):
    nodes_v1, nodes_v2 = versions_data
    results = VersionService.match_nodes(nodes_v1, nodes_v2)

    # Section 3.2: 40 mmHg -> 30 mmHg
    res_3_2 = [r for r in results if r.old_node and r.old_node.section_number == "3.2"][0]
    assert res_3_2.status == "MODIFIED"
    assert res_3_2.diff_summary is not None
    assert any("30 mmHg" in l for l in res_3_2.diff_summary["added_lines"])
    assert any("40 mmHg" in l for l in res_3_2.diff_summary["removed_lines"])

    # Section 4.2: E3 deflate time 2s -> 1.5s, added E6
    res_4_2 = [r for r in results if r.old_node and r.old_node.section_number == "4.2"][0]
    assert res_4_2.status == "MODIFIED"

    # Section 2.1.1.1: 300 cycles -> 250 cycles, 15% -> 10%
    res_2_1_1_1 = [r for r in results if r.old_node and r.old_node.section_number == "2.1.1.1"][0]
    assert res_2_1_1_1.status == "MODIFIED"

def test_version_matching_added_sections(versions_data):
    nodes_v1, nodes_v2 = versions_data
    results = VersionService.match_nodes(nodes_v1, nodes_v2)

    # Section 5.3 Data Export is ADDED in v2
    added = [r for r in results if r.status == "ADDED"]
    assert len(added) == 1
    assert added[0].new_node.section_number == "5.3"
    assert "Data Export" in added[0].new_node.heading
