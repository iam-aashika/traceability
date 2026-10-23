import re
from pathlib import Path
from typing import Dict, Any, List
import fitz
from app.services.ocr_service import OCRService
from app.utils.normalization import normalize_text

class PDFInspector:
    @staticmethod
    def inspect(file_path: str) -> Dict[str, Any]:
        """
        Perform complete static inspection of a PDF document prior to extraction.
        Identifies pages, fonts, ligatures, headings, tables, and structural anomalies.
        """
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"PDF file not found at {file_path}")

        doc = fitz.open(str(path))
        total_pages = len(doc)
        metadata = doc.metadata

        pages_summary = []
        font_occurrences: Dict[str, int] = {}
        detected_headings: List[Dict[str, Any]] = []
        table_counts = 0
        ligatures_detected = False
        scanned_pages = []
        raw_heading_numbers = []

        for p_idx, page in enumerate(doc):
            p_num = p_idx + 1
            raw_text = page.get_text()
            
            # Check for ligatures
            if any(lig in raw_text for lig in ["\ufb00", "\ufb01", "\ufb02", "\ufb03", "\ufb04"]):
                ligatures_detected = True

            is_scanned = OCRService.is_scanned_page(page)
            if is_scanned:
                scanned_pages.append(p_num)

            # Check tables
            tabs = page.find_tables()
            t_count = len(tabs.tables) if hasattr(tabs, "tables") else 0
            table_counts += t_count

            # Analyze fonts and blocks
            dict_data = page.get_text("dict")
            for block in dict_data.get("blocks", []):
                if block.get("type") == 0:  # text
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_key = f"{span.get('font')} ({round(span.get('size'), 1)}pt)"
                            font_occurrences[font_key] = font_occurrences.get(font_key, 0) + len(span.get("text", ""))
                            
                            text = span.get("text", "").strip()
                            size = round(span.get("size"), 1)
                            flags = span.get("flags", 0)
                            # In PyMuPDF: bit 4 (16) is bold, bit 2 (4) is serif
                            is_bold = bool((flags & 16) or ("bold" in span.get("font", "").lower()))

                            # Check for potential section heading (e.g. 1. Device Overview, 3.2 Cuff Inflation)
                            match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Za-z].*)$", text)
                            if match and (is_bold or size >= 12.0):
                                sec_num = match.group(1)
                                # Filter out false numbers like 200 from CT-200
                                if int(sec_num.split(".")[0]) <= 20:
                                    title = match.group(2).strip()
                                    raw_heading_numbers.append(sec_num)
                                    detected_headings.append({
                                        "page": p_num,
                                        "section_number": sec_num,
                                        "title": normalize_text(title),
                                        "font_size": size,
                                        "is_bold": is_bold,
                                        "font": span.get("font")
                                    })

            pages_summary.append({
                "page": p_num,
                "char_count": len(raw_text),
                "is_scanned": is_scanned,
                "tables_found": t_count
            })

        # Identify structural irregularities
        structural_warnings = []
        if ligatures_detected:
            structural_warnings.append("Unicode ligatures detected (e.g. fi, fl, ff) requiring NFKD normalization.")
        
        # Check duplicate titles
        titles = [h["title"] for h in detected_headings]
        dupes = {t for t in titles if titles.count(t) > 1}
        if dupes:
            structural_warnings.append(f"Duplicate heading titles detected: {list(dupes)}.")

        # Check out-of-order section numbers
        # e.g., 3.4 appearing before 3.3
        for i in range(len(raw_heading_numbers) - 1):
            curr_parts = [int(p) for p in raw_heading_numbers[i].split(".") if p.isdigit()]
            next_parts = [int(p) for p in raw_heading_numbers[i+1].split(".") if p.isdigit()]
            if curr_parts and next_parts and len(curr_parts) == len(next_parts) and curr_parts[:-1] == next_parts[:-1]:
                if curr_parts[-1] > next_parts[-1]:
                    structural_warnings.append(
                        f"Out-of-order section numbering detected: {raw_heading_numbers[i]} appears before {raw_heading_numbers[i+1]}."
                    )

        # Check skipped levels (e.g., 2.1 to 2.1.1.1)
        for num in raw_heading_numbers:
            parts = num.split(".")
            if len(parts) >= 4 and not any(h["section_number"] == ".".join(parts[:3]) for h in detected_headings):
                structural_warnings.append(
                    f"Hierarchy level skipping detected: {num} exists without parent {'.'.join(parts[:3])}."
                )

        return {
            "file_name": path.name,
            "total_pages": total_pages,
            "metadata": metadata,
            "scanned_pages": scanned_pages,
            "has_selectable_text": len(scanned_pages) < total_pages,
            "total_tables_detected": table_counts,
            "font_occurrences": font_occurrences,
            "detected_headings": detected_headings,
            "structural_warnings": structural_warnings,
            "pages_summary": pages_summary
        }
