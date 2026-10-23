import pytest
from app.services.pdf_extractor import PDFExtractor
from app.services.hierarchy_builder import HierarchyBuilder

V1_PATH = "data/ct200_manual_v1.pdf"

@pytest.fixture(scope="module")
def v1_nodes():
    title, raw_sections, _ = PDFExtractor.extract_document(V1_PATH)
    return HierarchyBuilder.build_hierarchy("doc_test", "ver_v1", raw_sections)

def test_irregularity_duplicate_headings(v1_nodes):
    """
    Assert duplicate heading title 'Error Codes' produces two distinct node IDs,
    distinct logical IDs, and correct distinct parents.
    """
    e_4_2 = [n for n in v1_nodes if n.section_number == "4.2"][0]
    e_7_1 = [n for n in v1_nodes if n.section_number == "7.1"][0]

    assert e_4_2.heading == "Error Codes"
    assert e_7_1.heading == "Error Codes"

    # Distinct unique IDs
    assert e_4_2.id != e_7_1.id
    assert e_4_2.logical_node_id != e_7_1.logical_node_id
    assert e_4_2.logical_node_id == "sec_4_2_error_codes"
    assert e_7_1.logical_node_id == "sec_7_1_error_codes"

    # Distinct parents
    assert e_4_2.parent_id != e_7_1.parent_id
    p_4 = [n for n in v1_nodes if n.section_number == "4"][0]
    p_7 = [n for n in v1_nodes if n.section_number == "7"][0]
    assert e_4_2.parent_id == p_4.id
    assert e_7_1.parent_id == p_7.id

def test_irregularity_skipped_hierarchy_level(v1_nodes):
    """
    Assert 2.1.1.1 (Level 4) is correctly attached to 2.1 (Level 2)
    when level 2.1.1 is omitted.
    """
    n_2_1_1_1 = [n for n in v1_nodes if n.section_number == "2.1.1.1"][0]
    n_2_1 = [n for n in v1_nodes if n.section_number == "2.1"][0]

    assert n_2_1_1_1.parent_id == n_2_1.id
    assert n_2_1_1_1.level == 4
    assert "skipped" in n_2_1_1_1.extraction_warnings.lower()

def test_irregularity_out_of_order_section_numbering(v1_nodes):
    """
    Assert 3.4 appearing before 3.3 in document order are both parented under Section 3
    without throwing parent lookup errors or corrupting parentage.
    """
    s_3_4 = [n for n in v1_nodes if n.section_number == "3.4"][0]
    s_3_3 = [n for n in v1_nodes if n.section_number == "3.3"][0]
    p_3 = [n for n in v1_nodes if n.section_number == "3"][0]

    assert s_3_4.order_index < s_3_3.order_index
    assert s_3_4.parent_id == p_3.id
    assert s_3_3.parent_id == p_3.id

def test_numbered_list_items_not_promoted_to_headings(v1_nodes):
    """
    Assert clinical classification items (1. Normal, 2. Elevated...) are kept
    inside the body text of 3.3 and not parsed as bogus Level 1 root sections.
    """
    s_3_3 = [n for n in v1_nodes if n.section_number == "3.3"][0]
    assert "Normal: systolic < 120" in s_3_3.body_text
    assert "Hypertensive Crisis" in s_3_3.body_text

    # Verify no fake Level 1 nodes for 1, 2, 3, 4, 5 were created
    root_nodes = [n for n in v1_nodes if n.level == 1]
    assert len(root_nodes) == 8  # Sections 1 through 8 only
