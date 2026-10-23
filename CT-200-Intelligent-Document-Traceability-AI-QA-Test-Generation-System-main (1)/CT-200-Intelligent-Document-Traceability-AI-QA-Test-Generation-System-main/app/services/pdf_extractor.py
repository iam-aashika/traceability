import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional
import fitz
from app.utils.normalization import normalize_text
from app.services.ocr_service import OCRService

logger = logging.getLogger(__name__)

class RawSectionItem:
    def __init__(
        self,
        section_number: Optional[str],
        heading: str,
        level: int,
        page_start: int,
        page_end: int,
        body_text: str = "",
        has_table: bool = False,
        table_data: Optional[Any] = None,
        confidence: float = 1.0,
        warnings: Optional[List[str]] = None
    ):
        self.section_number = section_number
        self.heading = heading
        self.level = level
        self.page_start = page_start
        self.page_end = page_end
        self.body_text = body_text
        self.has_table = has_table
        self.table_data = table_data
        self.confidence = confidence
        self.warnings = warnings or []

class PDFExtractor:
    @staticmethod
    def extract_document(file_path: str) -> Tuple[str, List[RawSectionItem], List[str]]:
        """
        Extract document title and ordered raw section items from a CT-200 PDF.
        Returns:
            (document_title, raw_sections, extraction_warnings)
        """
        doc = fitz.open(file_path)
        global_warnings: List[str] = []
        document_title = "CardioTrack CT-200 Home Blood Pressure Monitor"
        raw_sections: List[RawSectionItem] = []
        current_section: Optional[RawSectionItem] = None

        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1

            # Check if scanned
            if OCRService.is_scanned_page(page):
                global_warnings.append(f"Page {page_num} is image-only/scanned. Applying OCR.")
                text, ocr_warn = OCRService.extract_text_with_ocr(page)
                global_warnings.extend(ocr_warn)

            # Identify tables on this page to avoid duplicating or scrambling text
            page_tables = []
            try:
                tabs = page.find_tables()
                if hasattr(tabs, "tables"):
                    for tab in tabs.tables:
                        # Extract table rows
                        extracted_rows = tab.extract()
                        if extracted_rows and len(extracted_rows) > 1:
                            # Clean each cell
                            clean_rows = []
                            for row in extracted_rows:
                                clean_rows.append([normalize_text(cell or "") for cell in row])
                            page_tables.append({
                                "bbox": tab.bbox,
                                "rows": clean_rows
                            })
            except Exception as e:
                logger.warning(f"Error extracting tables on page {page_num}: {e}")

            # Extract structured text lines with font properties
            dict_data = page.get_text("dict")
            blocks = dict_data.get("blocks", [])

            for block in blocks:
                if block.get("type") != 0:  # Not text
                    continue

                bbox = block.get("bbox", (0, 0, 0, 0))
                
                # Check if this block falls inside an extracted table
                inside_table = False
                matching_table = None
                for pt in page_tables:
                    tb = pt["bbox"]
                    # If vertical overlap with table
                    if bbox[1] >= tb[1] - 5 and bbox[3] <= tb[3] + 5 and bbox[0] >= tb[0] - 5:
                        inside_table = True
                        matching_table = pt
                        break

                if inside_table and matching_table:
                    # Append table data to current section once
                    if current_section and not current_section.has_table:
                        current_section.has_table = True
                        current_section.table_data = matching_table["rows"]
                        # Convert table to clean Markdown format for body_text
                        md_table = PDFExtractor._format_markdown_table(matching_table["rows"])
                        if current_section.body_text:
                            current_section.body_text += f"\n\n{md_table}"
                        else:
                            current_section.body_text = md_table
                        current_section.page_end = page_num
                    continue

                # Process text lines
                for line in block.get("lines", []):
                    line_text = ""
                    max_size = 0.0
                    is_bold = False

                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        line_text += span_text
                        size = round(span.get("size", 11.0), 1)
                        if size > max_size:
                            max_size = size
                        flags = span.get("flags", 0)
                        font_name = span.get("font", "").lower()
                        # In PyMuPDF: bit 4 (16) is bold. Bit 2 (4) is serifed.
                        if (flags & 16) or ("bold" in font_name):
                            is_bold = True

                    line_text = normalize_text(line_text).strip()
                    if not line_text:
                        continue

                    # Document Title detection on Page 1 (font size ~22pt)
                    if page_num == 1 and max_size >= 20.0:
                        if "CardioTrack" in line_text or "Blood Pressure" in line_text or "Manual" in line_text:
                            if "Technical" in line_text:
                                document_title = line_text
                            continue

                    # Section heading pattern match
                    # e.g. "1. Device Overview", "2.1 General Specifications", "2.1.1.1 Battery Life"
                    heading_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$", line_text)

                    # Distinguish genuine heading from numbered lists (e.g. 1. Normal: systolic...)
                    # Real headings have is_bold == True or max_size >= 12.0
                    is_genuine_heading = False
                    if heading_match and is_bold:
                        is_genuine_heading = True
                    elif heading_match and max_size >= 12.0:
                        is_genuine_heading = True

                    if is_genuine_heading:
                        sec_num = heading_match.group(1)
                        heading_title = heading_match.group(2).strip()
                        
                        # Determine level based on dot count in section number
                        dot_count = sec_num.count(".")
                        level = dot_count + 1

                        # Save previous section
                        if current_section:
                            current_section.body_text = normalize_text(current_section.body_text)
                            raw_sections.append(current_section)

                        warnings = []
                        if level > 2 and dot_count > 1:
                            warnings.append(f"Deep subsection level ({level}) detected for {sec_num}.")

                        current_section = RawSectionItem(
                            section_number=sec_num,
                            heading=heading_title,
                            level=level,
                            page_start=page_num,
                            page_end=page_num,
                            body_text="",
                            confidence=1.0,
                            warnings=warnings
                        )
                    else:
                        # Body text line
                        if current_section:
                            current_section.page_end = page_num
                            if current_section.body_text:
                                # Check if previous line ended without terminal punctuation (hyphenation or page break)
                                if current_section.body_text.endswith("-"):
                                    current_section.body_text = current_section.body_text[:-1] + line_text
                                else:
                                    current_section.body_text += " " + line_text
                            else:
                                current_section.body_text = line_text

        # Append last section
        if current_section:
            current_section.body_text = normalize_text(current_section.body_text)
            raw_sections.append(current_section)

        return document_title, raw_sections, global_warnings

    @staticmethod
    def _format_markdown_table(rows: List[List[str]]) -> str:
        """Format 2D table array into standard GitHub-flavored markdown table."""
        if not rows:
            return ""
        col_count = max(len(row) for row in rows)
        if col_count == 0:
            return ""

        padded_rows = []
        for row in rows:
            clean_row = [r.replace("\n", " ").strip() for r in row]
            while len(clean_row) < col_count:
                clean_row.append("")
            padded_rows.append(clean_row)

        header = padded_rows[0]
        separator = ["---"] * col_count
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(separator) + " |"
        ]
        for row in padded_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)
