import os
import logging
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SimpleFileNodeParser

# ─── Logger Setup ─────────────────────────────────────────────────────────────
def setup_logger(name=__name__, level=logging.INFO):
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    logging.basicConfig(format=fmt, level=level)
    return logging.getLogger(name)

logger = setup_logger()

# ─── Parsing & Metadata ────────────────────────────────────────────────────────

def parse_contract(file_path: str):
    """
    Parses a contract PDF into nodes using default LlamaIndex metadata.
    """
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Loading contract document: %s", file_path)
    reader = SimpleDirectoryReader(input_files=[file_path])
    documents = reader.load_data()

    if not documents:
        logger.error("No document data found.")
        raise ValueError("No document data found.")

    logger.info("Contract document loaded successfully.")
    
    parser = SimpleFileNodeParser()
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