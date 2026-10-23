import logging
from typing import Tuple, List
import fitz
from PIL import Image
import io
import pytesseract
from app.config import settings

logger = logging.getLogger(__name__)

if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

class OCRService:
    @staticmethod
    def is_scanned_page(page: fitz.Page, min_char_threshold: int = 50) -> bool:
        """
        Determine if a page lacks a selectable text layer and relies on raster images.
        """
        text = page.get_text().strip()
        images = page.get_images()
        return len(text) < min_char_threshold and len(images) > 0

    @staticmethod
    def extract_text_with_ocr(page: fitz.Page) -> Tuple[str, List[str]]:
        """
        Render a PDF page to an image and run Tesseract OCR.
        Returns (extracted_text, warnings).
        """
        warnings = []
        try:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            return text, warnings
        except pytesseract.TesseractNotFoundError:
            msg = "Tesseract executable not found on host. OCR fallback skipped."
            logger.warning(msg)
            warnings.append(msg)
            return page.get_text(), warnings
        except Exception as e:
            msg = f"OCR processing encountered an error: {str(e)}"
            logger.error(msg)
            warnings.append(msg)
            return page.get_text(), warnings
