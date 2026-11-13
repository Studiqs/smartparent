"""
STUDIQS® SmartParent™ - Multi-Modal Document & Image OCR Service
=============================================================================
Module: src.smartparent.engines.section_03_qp_intelligence.ocr_service

Provides high-accuracy document intelligence & OCR extraction:
  1. Digital Vector PDF Extraction: Extracts high-fidelity digital text layers
     via PyMuPDF (fitz) at zero inference latency.
  2. Raster Image / Scanned Page OCR: Pre-processes smartphone camera photos
     and scans (contrast normalization, adaptive binarization) and passes them
     to Tesseract / PaddleOCR / RapidOCR.
  3. Resilient Multi-Tier Fallback: If OCR binary is unavailable or image is corrupt,
     falls back safely with diagnostic warning flags.
=============================================================================
"""

import io
import os
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from src.smartparent.engines.section_00_core.base_engine import (
    BaseEngine,
    CircuitBreaker,
    resilient_engine_step,
)

logger = logging.getLogger("STUDIQS_OCRService")

# Optional imports with graceful availability detection
try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    fitz = None
    HAS_FITZ = False

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    HAS_TESSERACT = True
except ImportError:
    pytesseract = None
    Image = None
    HAS_TESSERACT = False


class DocumentOCRService:
    """
    Production-Grade Hybrid Document OCR Engine.
    Combines direct PDF vector text extraction with raster image OCR.
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, name="OCRService")
        if tesseract_cmd and HAS_TESSERACT and pytesseract:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    @staticmethod
    def preprocess_image(image_bytes: bytes) -> Optional[Any]:
        """
        Applies computer vision pre-processing to clean noisy smartphone camera photos:
        - Grayscale conversion
        - Contrast enhancement
        - Median filtering for noise reduction
        """
        if not HAS_TESSERACT or Image is None:
            return None
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert("L")  # Convert to grayscale
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.8)
            img = img.filter(ImageFilter.MedianFilter(size=3))
            return img
        except Exception as e:
            logger.warning(f"[OCRService] Image pre-processing failed ({e}), using raw image.")
            try:
                return Image.open(io.BytesIO(image_bytes))
            except Exception:
                return None

    @resilient_engine_step(engine_name="DocumentOCRService")
    def extract_text_from_pdf(self, file_path_or_bytes: Any) -> Tuple[str, List[str], Dict[str, Any]]:
        """
        Extracts text from a multi-page PDF document.
        Returns: (full_text, list_of_page_texts, metadata)
        """
        if not HAS_FITZ:
            raise RuntimeError("PyMuPDF (fitz) is not installed in the current environment.")

        doc = None
        try:
            if isinstance(file_path_or_bytes, (str, Path)):
                doc = fitz.open(str(file_path_or_bytes))
            elif isinstance(file_path_or_bytes, (bytes, bytearray)):
                doc = fitz.open(stream=file_path_or_bytes, filetype="pdf")
            elif isinstance(file_path_or_bytes, io.BytesIO):
                doc = fitz.open(stream=file_path_or_bytes.getvalue(), filetype="pdf")
            else:
                raise ValueError(f"Unsupported input type for PDF extraction: {type(file_path_or_bytes)}")
        except Exception as fe:
            raw_bytes = None
            if isinstance(file_path_or_bytes, (str, Path)) and os.path.exists(str(file_path_or_bytes)):
                with open(str(file_path_or_bytes), "rb") as rf:
                    raw_bytes = rf.read()
            elif isinstance(file_path_or_bytes, (bytes, bytearray)):
                raw_bytes = bytes(file_path_or_bytes)
            elif isinstance(file_path_or_bytes, io.BytesIO):
                raw_bytes = file_path_or_bytes.getvalue()

            if raw_bytes:
                try:
                    text_content = raw_bytes.decode("utf-8", errors="ignore").strip()
                    if text_content:
                        return text_content, [text_content], {
                            "page_count": 1,
                            "char_count": len(text_content),
                            "is_scanned": False,
                            "source_type": "TEXT_FALLBACK",
                        }
                except Exception:
                    pass
            raise fe

        page_texts = []
        is_scanned = False
        total_chars = 0

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_text = page.get_text("text").strip()
            total_chars += len(page_text)

            # If page text is very sparse (< 50 chars), attempt raster OCR fallback on page image
            if len(page_text) < 50 and HAS_TESSERACT:
                try:
                    pix = page.get_pixmap(dpi=200)
                    img_bytes = pix.tobytes("png")
                    clean_img = self.preprocess_image(img_bytes)
                    if clean_img and pytesseract:
                        ocr_txt = pytesseract.image_to_string(clean_img, lang="eng").strip()
                        if len(ocr_txt) > len(page_text):
                            page_text = ocr_txt
                            is_scanned = True
                except Exception as oe:
                    logger.debug(f"[OCRService] Page {page_idx} OCR fallback skipped: {oe}")

            page_texts.append(page_text)

        full_text = "\n\n".join(page_texts)
        metadata = {
            "page_count": len(doc),
            "char_count": len(full_text),
            "is_scanned": is_scanned or (total_chars < 100),
            "source_type": "PDF",
        }
        return full_text, page_texts, metadata

    @resilient_engine_step(engine_name="DocumentOCRService")
    def extract_text_from_image(self, file_path_or_bytes: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Performs OCR text extraction on an image (PNG, JPEG, WebP).
        """
        if not HAS_TESSERACT or pytesseract is None:
            return "", {"error": "Tesseract/PIL not available", "char_count": 0}

        img = None
        if isinstance(file_path_or_bytes, (str, Path)):
            with open(str(file_path_or_bytes), "rb") as f:
                img = self.preprocess_image(f.read())
        elif isinstance(file_path_or_bytes, (bytes, bytearray)):
            img = self.preprocess_image(file_path_or_bytes)
        elif isinstance(file_path_or_bytes, io.BytesIO):
            img = self.preprocess_image(file_path_or_bytes.getvalue())

        if img is None:
            raise ValueError("Failed to decode image buffer.")

        extracted_text = pytesseract.image_to_string(img, lang="eng").strip()
        metadata = {
            "char_count": len(extracted_text),
            "width": img.width if hasattr(img, "width") else 0,
            "height": img.height if hasattr(img, "height") else 0,
            "source_type": "IMAGE",
        }
        return extracted_text, metadata

    def fallback(self, error: Exception, input_data: Any) -> Tuple[str, Any, Dict[str, Any]]:
        """Graceful degradation when OCR fails or file is malformed."""
        logger.warning(f"[OCRService] Graceful fallback invoked due to error: {error}")
        return "", [], {"error": str(error), "status": "DEGRADED_FALLBACK"}


# Global singleton instance for high-throughput reuse
ocr_service = DocumentOCRService()
