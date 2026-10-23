import pytest
from pathlib import Path
from app.services.pdf_extractor import PDFExtractor
from app.services.pdf_inspector import PDFInspector
from app.services.ocr_service import OCRService
from app.services.hash_service import HashService
from app.utils.normalization import normalize_text, canonical_content_for_hash

V1_PATH = "data/ct200_manual_v1.pdf"
V2_PATH = "data/ct200_manual_v2.pdf"

def test_normalization_decomposes_ligatures():
    # \ufb00 is ff, \ufb01 is fi, \ufb02 is fl
    text_with_ligatures = "Cu\ufb00 In\ufb02ation Speci\ufb01cations"
    normalized = normalize_text(text_with_ligatures)
    assert normalized == "Cuff Inflation Specifications"
    assert "\ufb00" not in normalized
    assert "\ufb01" not in normalized
    assert "\ufb02" not in normalized

def test_pdf_inspector_diagnostics():
    report = PDFInspector.inspect(V1_PATH)
    assert report["total_pages"] == 6
    assert report["has_selectable_text"] is True
    assert len(report["detected_headings"]) > 0
    # Confirms structural warnings detected (ligatures, out-of-order, skipped levels, duplicate headings)
    assert any("ligatures" in w.lower() for w in report["structural_warnings"])
    assert any("duplicate" in w.lower() for w in report["structural_warnings"])
    assert any("out-of-order" in w.lower() for w in report["structural_warnings"])

def test_pdf_extractor_v1():
    title, sections, warnings = PDFExtractor.extract_document(V1_PATH)
    assert "CardioTrack" in title
    assert len(sections) == 27
    
    # Verify tables extracted under 2.1 and 4.2
    s_2_1 = [s for s in sections if s.section_number == "2.1"][0]
    assert s_2_1.has_table is True
    assert "Oscillometric" in s_2_1.body_text

    s_4_2 = [s for s in sections if s.section_number == "4.2"][0]
    assert s_4_2.has_table is True
    assert "E1" in s_4_2.body_text
    assert "E5" in s_4_2.body_text

def test_pdf_extractor_v2_new_section():
    title, sections, warnings = PDFExtractor.extract_document(V2_PATH)
    assert len(sections) == 28
    # Section 5.3 Data Export exists only in v2
    sec_5_3 = [s for s in sections if s.section_number == "5.3"]
    assert len(sec_5_3) == 1
    assert "Data Export" in sec_5_3[0].heading
    assert "CSV" in sec_5_3[0].body_text

def test_content_hashing_consistency():
    h1 = HashService.calculate_content_hash("Cuff Inflation", "Increments of 40 mmHg.")
    h2 = HashService.calculate_content_hash("Cuff Inflation", "Increments of 40 mmHg.  ")
    h3 = HashService.calculate_content_hash("Cuff Inflation", "Increments of 30 mmHg.")
    
    # Whitespace padding does not alter canonical hash
    assert h1 == h2
    # Semantic content change alters hash
    assert h1 != h3
