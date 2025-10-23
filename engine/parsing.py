import os
import logging
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SimpleNodeParser  # CHANGED
from config.settings import settings as app_settings  # ADDED

# ─── Logger Setup ─────────────────────────────────────────────────────────────
# Use standard logging setup, as main.py configures the root logger
logger = logging.getLogger(__name__)

# ─── Parsing & Metadata ────────────────────────────────────────────────────────

def parse_contract(file_path: str):
    """
    Parses a contract PDF into nodes using SimpleNodeParser for chunking.
    """
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Loading contract document: %s", file_path)
    reader = SimpleDirectoryReader(input_files=[file_path])
    documents = reader.load_data()

    if not documents:
        logger.error("No document data found in %s.", file_path)
        # Return empty list to be handled by the caller
        return []

    logger.info("Contract document loaded successfully.")
    
    # CHANGED: Use SimpleNodeParser with settings from config
    parser = SimpleNodeParser.from_defaults(
        chunk_size=app_settings.CHUNK_SIZE,
        chunk_overlap=app_settings.CHUNK_OVERLAP
    )
    
    nodes = parser.get_nodes_from_documents(documents)

    logger.info("Contract parsed into %d nodes.", len(nodes))
    return nodes


def extract_metadata(nodes):
    """
    Extracts and aggregates metadata from parsed nodes.
    """
    metadata = {}
    for node in nodes:
        for key, value in node.metadata.items():
            metadata.setdefault(key, []).append(value)
    return metadata


# ─── Example Usage ─────────────────────────────────────────────────────────────
# if __name__ == "__main__":
    # Already configured via setup_logger()
    try:
        nodes = parse_contract("../data/contracts/sample.pdf")
        for i, node in enumerate(nodes, 1):
            logger.info("Node %d content:\n%s", i, node.get_content())
            logger.info("Node %d metadata: %s", i, node.metadata)
        meta = extract_metadata(nodes)
        logger.info("Aggregated metadata: %s", meta)
    except Exception as e:
        logger.exception("An error occurred while parsing the contract")
        