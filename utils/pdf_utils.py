"""PDF extraction utilities with multi-strategy fallback and relevance filtering."""
from __future__ import annotations

import re
import hashlib
from typing import List, Tuple, Optional
from pathlib import Path

from pypdf import PdfReader
from utils.cache import get_json, set_json, key_hash

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

try:
    from pdf2image import convert_from_path  # requires poppler
    import pytesseract  # requires Tesseract OCR binary
except Exception:  # pragma: no cover
    convert_from_path = None  # type: ignore
    pytesseract = None  # type: ignore


def _alpha_ratio(s: str) -> float:
    if not s:
        return 0.0
    letters = sum(c.isalpha() for c in s)
    return letters / max(1, len(s))


def _filter_relevant(text_by_pages: List[str], *, min_line_len: int = 20, min_alpha_ratio: float = 0.2) -> List[str]:
    """Basic relevance filter: remove headers/footers, page numbers, very short/noisy lines."""
    # Split pages into lines
    pages_lines: List[List[str]] = [p.splitlines() for p in text_by_pages]
    if not pages_lines:
        return []

    # Detect common headers/footers (first/last non-empty line on a page)
    headers = {}
    footers = {}
    for lines in pages_lines:
        non_empty = [ln.strip() for ln in lines if ln.strip()]
        if not non_empty:
            continue
        headers[non_empty[0]] = headers.get(non_empty[0], 0) + 1
        footers[non_empty[-1]] = footers.get(non_empty[-1], 0) + 1

    page_count = len(pages_lines)
    def is_common(s: str, table: dict) -> bool:
        return table.get(s, 0) >= max(2, int(0.5 * page_count))

    # Filters
    page_num_pattern = re.compile(r"^(page\s*\d+|\d+)$", re.IGNORECASE)

    filtered_pages: List[str] = []
    for lines in pages_lines:
        out_lines: List[str] = []
        for idx, raw in enumerate(lines):
            s = raw.strip()
            if not s:
                continue
            if len(s) < min_line_len:
                continue
            if _alpha_ratio(s) < min_alpha_ratio:
                continue
            if page_num_pattern.match(s):
                continue
            # remove lines that are common header/footer
            # Note: compute non-empty list again to align with detection
            # This is a simple heuristic; OK for now
            if is_common(s, headers) or is_common(s, footers):
                continue
            out_lines.append(s)
        # Collapse multiple blank lines
        filtered_pages.append("\n".join(out_lines))
    return filtered_pages


def _extract_with_pypdf(file_path: Path) -> List[str]:
    texts: List[str] = []
    with open(file_path, "rb") as fh:
        reader = PdfReader(fh)
        for page in reader.pages:
            t = page.extract_text() or ""
            texts.append(t)
    return texts


def _extract_with_pymupdf(file_path: Path) -> List[str]:
    if not fitz:
        return []
    texts: List[str] = []
    doc = fitz.open(file_path)
    try:
        for page in doc:
            t = page.get_text("text") or ""
            texts.append(t)
    finally:
        doc.close()
    return texts


def _extract_with_ocr(file_path: Path, *, dpi: int = 200, lang: str = "eng") -> List[str]:
    if not convert_from_path or not pytesseract:
        return []
    pages = convert_from_path(str(file_path), dpi=dpi)
    out: List[str] = []
    for img in pages:
        text = pytesseract.image_to_string(img, lang=lang) or ""
        out.append(text)
    return out


def _fast_file_hash(file_path: Path) -> str:
    """Quick hash of file metadata (size + mtime) for cache keys."""
    try:
        stat = file_path.stat()
        return hashlib.md5(f"{stat.st_size}_{stat.st_mtime}".encode()).hexdigest()
    except Exception:
        return "unknown"

def extract_pdf_text(
    file_path: Path,
    *,
    enable_ocr: bool = False,
    ocr_lang: str = "eng",
    min_alpha_ratio: float = 0.2,
    min_line_len: int = 20,
    logger=None,
) -> str:
    """Extract text with pypdf -> PyMuPDF -> OCR fallback, then filter relevance.
    
    Uses persistent caching to avoid re-processing unchanged files.
    """
    # Check cache first
    file_hash = _fast_file_hash(file_path)
    # Include parameters in cache key to handle config changes
    config_hash = key_hash({
        "ocr": enable_ocr, 
        "lang": ocr_lang, 
        "alpha": min_alpha_ratio, 
        "len": min_line_len
    })
    cache_key = f"pdf_text_v1:{file_hash}:{config_hash}"
    
    cached_text = get_json(cache_key)
    if cached_text is not None:
        if logger:
            logger.debug(f"Cache hit for PDF extraction: {file_path.name}")
        return cached_text

    # Proceed with extraction
    pages = _extract_with_pypdf(file_path)
    total_txt = "".join(pages)
    if len(total_txt.strip()) == 0 or _alpha_ratio(total_txt) < 0.05:
        if logger:
            logger.info("pypdf found little/no text; trying PyMuPDF fallback: %s", file_path)
        pages = _extract_with_pymupdf(file_path) or pages

    if (len("".join(pages).strip()) == 0 or _alpha_ratio("".join(pages)) < 0.05) and enable_ocr:
        if logger:
            logger.warning("PDF appears scanned; attempting OCR (this may be slow): %s", file_path)
        ocr_pages = _extract_with_ocr(file_path, lang=ocr_lang)
        if ocr_pages:
            pages = ocr_pages
        elif logger:
            logger.error("OCR not available or failed. Ensure Poppler and Tesseract are installed.")

    filtered_pages = _filter_relevant(pages, min_line_len=min_line_len, min_alpha_ratio=min_alpha_ratio)
    result_text = "\n\n".join(p for p in filtered_pages if p.strip())
    
    # Cache the result (long TTL for file content)
    set_json(cache_key, result_text, tier="pdf_text")
    
    return result_text


def extract_pdf_pages_text(
    file_path: Path,
    *,
    enable_ocr: bool = False,
    ocr_lang: str = "eng",
    min_alpha_ratio: float = 0.2,
    min_line_len: int = 20,
    logger=None,
) -> List[str]:
    """Same as extract_pdf_text but returns filtered text by page.
    
    Uses persistent caching.
    """
    # Check cache first
    file_hash = _fast_file_hash(file_path)
    config_hash = key_hash({
        "ocr": enable_ocr, 
        "lang": ocr_lang, 
        "alpha": min_alpha_ratio, 
        "len": min_line_len,
        "mode": "pages"
    })
    cache_key = f"pdf_pages_v1:{file_hash}:{config_hash}"
    
    cached_pages = get_json(cache_key)
    if cached_pages is not None:
        if logger:
            logger.debug(f"Cache hit for PDF pages extraction: {file_path.name}")
        return cached_pages

    pages = _extract_with_pypdf(file_path)
    total_txt = "".join(pages)
    if len(total_txt.strip()) == 0 or _alpha_ratio(total_txt) < 0.05:
        if logger:
            logger.info("pypdf found little/no text; trying PyMuPDF fallback: %s", file_path)
        pages2 = _extract_with_pymupdf(file_path)
        if pages2:
            pages = pages2
    if (len("".join(pages).strip()) == 0 or _alpha_ratio("".join(pages)) < 0.05) and enable_ocr:
        if logger:
            logger.warning("PDF appears scanned; attempting OCR (this may be slow): %s", file_path)
        ocr_pages = _extract_with_ocr(file_path, lang=ocr_lang)
        if ocr_pages:
            pages = ocr_pages
        elif logger:
            logger.error("OCR not available or failed. Ensure Poppler and Tesseract are installed.")
    filtered_pages = _filter_relevant(pages, min_line_len=min_line_len, min_alpha_ratio=min_alpha_ratio)
    result_pages = [p for p in filtered_pages if p.strip()]
    
    # Cache the result
    set_json(cache_key, result_pages, tier="pdf_text")
    
    return result_pages
