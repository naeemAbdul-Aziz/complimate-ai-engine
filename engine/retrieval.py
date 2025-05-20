import logging
import os

from llama_index.core import (
    Document,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import QueryBundle
from llama_index.retrievers.bm25 import BM25Retriever
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)


def load_or_create_regulation_index(regulation_text):
    """
    Loads an existing regulation index or creates a new one if it doesn't exist.

    Args:
        regulation_text (str): The text content of the regulation document

    Returns:
        VectorStoreIndex: The index for the regulation text
    """

    logger = logging.getLogger(__name__)

    # Define the path for storing the index
    index_path = "data/regulation_index"

    # Check if the index already exists
    if os.path.exists(index_path) and len(os.listdir(index_path)) > 0:
        try:
            logger.info(f"Loading existing regulation index from {index_path}")
            storage_context = StorageContext.from_defaults(persist_dir=index_path)
            index = load_index_from_storage(storage_context)
            logger.info("Regulation index loaded successfully")
            return index
        except Exception as e:
            logger.error(f"Error loading existing index: {str(e)}")
            logger.info("Will create new regulation index instead")
    else:
        logger.info(f"No existing index found at {index_path}, creating new one")

    # Create a new index
    try:
        os.makedirs(index_path, exist_ok=True)
        documents = [Document(text=regulation_text, metadata={"source": "regulation"})]
        index = VectorStoreIndex.from_documents(documents)

        # Persist the index to disk
        logger.info(f"Saving regulation index to {index_path}")
        index.storage_context.persist(persist_dir=index_path)
        logger.info("Regulation index created and saved successfully")
        return index
    except Exception as e:
        logger.error(f"Error creating regulation index: {str(e)}")
        return None


def load_regulation_text(file_path):
    """
    Loads text from a regulation PDF file.

    Args:
        file_path (str): Path to the PDF file containing regulations

    Returns:
        str: Extracted text from the regulation PDF
    """

    logger = logging.getLogger(__name__)

    if not os.path.exists(file_path):
        logger.error(f"Regulation file not found: {file_path}")
        return None

    logger.info(f"Loading regulation text from: {file_path}")

    try:
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            text = ""

            total_pages = len(reader.pages)
            logger.info(f"Processing {total_pages} pages from regulation PDF")

            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n\n"

                if (i + 1) % 10 == 0 or (i + 1) == total_pages:
                    logger.info(f"Processed {i + 1}/{total_pages} pages")

            logger.info(
                f"Successfully extracted {len(text)} characters from regulation PDF"
            )
            return text
    except Exception as e:
        logger.error(f"Error loading regulation text: {str(e)}")
        return None


def find_relevant_regulations(contract_node, regulation_index, top_n=5):
    """
    Finds relevant regulations for a given contract node using hybrid search.

    Args:
        contract_node (llama_index.core.Node): A node from the contract.
        regulation_index (llama_index.core.VectorStoreIndex): Index of the regulation.
        top_n (int): The number of top results to consider.

    Returns:
        list: A list of retrieved nodes from the regulation, sorted by relevance.
    """
    bm25_retriever = BM25Retriever.from_defaults(index=regulation_index)
    vector_retriever = VectorIndexRetriever(index=regulation_index, similarity_top_k=3)

    query_bundle = QueryBundle(query_str=contract_node.get_content())
    bm25_results = bm25_retriever.retrieve(query_bundle)
    logger.info("✅ BM25 search results retrieved. Count: %d", len(bm25_results))

    vector_results = vector_retriever.retrieve(query_bundle)
    logger.info("✅ Vector search results retrieved. Count: %d", len(vector_results))

    all_results = bm25_results + vector_results
    all_results.sort(key=lambda x: x.score, reverse=True)
    logger.info(
        "✅ Hybrid search results merged. Total candidates: %d", len(all_results)
    )

    unique_results = []
    seen_texts = set()
    for result in all_results:
        content = result.node.get_content()
        if content not in seen_texts:
            unique_results.append(result)
            seen_texts.add(content)

    logger.info("🔎 Returning top %d unique results.", min(top_n, len(unique_results)))
    return unique_results[:top_n]
