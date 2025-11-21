import os
import logging
from typing import Iterable
from pypdf import PdfReader
from pathlib import Path
from llama_index.core.schema import Document
from llama_index.core.node_parser import SimpleNodeParser
from config.settings import settings as app_settings
from utils.pdf_utils import extract_pdf_pages_text

# Use standard logging setup, as main.py configures the root logger
logger = logging.getLogger(__name__)

def parse_contract(file_path: str) -> Iterable:
    """
    Parses a contract PDF into nodes using a memory-efficient, page-by-page
    streaming approach with SimpleNodeParser for chunking.
    """
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Loading contract document via streaming: %s", file_path)
    
    all_nodes = []
    try:
        parser = SimpleNodeParser.from_defaults(
            chunk_size=app_settings.CHUNK_SIZE,
            chunk_overlap=app_settings.CHUNK_OVERLAP
        )

        pages_text = extract_pdf_pages_text(
            Path(file_path),
            enable_ocr=app_settings.ENABLE_PDF_OCR,
            ocr_lang=app_settings.OCR_LANG,
            min_alpha_ratio=app_settings.PDF_TEXT_MIN_ALPHA_RATIO,
            min_line_len=app_settings.PDF_FILTER_MIN_LINE_LEN,
            logger=logger,
        )

        for i, page_text in enumerate(pages_text):
            if not page_text or page_text.isspace():
                continue
            page_doc = Document(
                text=page_text,
                metadata={"page_label": str(i + 1), "file_name": os.path.basename(file_path)}
            )
            nodes = parser.get_nodes_from_documents([page_doc])
            all_nodes.extend(nodes)
            logger.debug(f"Parsed page {i+1} into {len(nodes)} nodes.")

    except Exception as e:
        logger.exception(f"Failed to parse document {file_path}: {e}")
        # Return what has been parsed so far, or an empty list
        return all_nodes

    logger.info("Contract parsed into %d nodes.", len(all_nodes))
    return all_nodes


def extract_metadata(nodes):
    """
    Extracts and aggregates metadata from parsed nodes.
    """
    metadata = {}
    for node in nodes:
        for key, value in node.metadata.items():
            metadata.setdefault(key, []).append(value)
    return metadata