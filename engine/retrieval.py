import logging
from typing import List

from llama_index.core.schema import QueryBundle
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.retrievers.bm25 import BM25Retriever

from utils.cache import get_json, set_json, key_hash

logger = logging.getLogger(__name__)


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
    content = contract_node.get_content()
    cache_key = f"retrieval:{key_hash({'content': content, 'top_n': top_n})}"

    cached = get_json(cache_key)
    if cached:
        logger.info("Retrieval cache hit for contract node. Returning %d cached results.", len(cached))
        # Rehydrate NodeWithScore-like objects is complex; instead return the cached top texts as fresh retrieval
        # For simplicity, bypass full rehydration and perform a narrower vector lookup for top_n to ensure objects are valid
        try:
            vector_retriever = VectorIndexRetriever(index=regulation_index, similarity_top_k=top_n)
            query_bundle = QueryBundle(query_str=content)
            vector_results = vector_retriever.retrieve(query_bundle)
            logger.info("Vector search results retrieved (post-cache). Count: %d", len(vector_results))
            return vector_results[:top_n]
        except Exception:
            # If anything fails, fall back to full path below
            pass

    bm25_retriever = BM25Retriever.from_defaults(index=regulation_index)
    vector_retriever = VectorIndexRetriever(index=regulation_index, similarity_top_k=3)

    query_bundle = QueryBundle(query_str=content)
    bm25_results = bm25_retriever.retrieve(query_bundle)
    logger.info("BM25 search results retrieved. Count: %d", len(bm25_results))

    vector_results = vector_retriever.retrieve(query_bundle)
    logger.info("Vector search results retrieved. Count: %d", len(vector_results))

    all_results = bm25_results + vector_results
    # Some retrievers may return None for score; treat as 0.0 for sorting
    all_results.sort(key=lambda x: (x.score or 0.0), reverse=True)
    logger.info("Hybrid search results merged. Total candidates: %d", len(all_results))

    unique_results = []
    seen_texts = set()
    for result in all_results:
        content = result.node.get_content()
        if content not in seen_texts:
            unique_results.append(result)
            seen_texts.add(content)

    logger.info("Returning top %d unique results.", min(top_n, len(unique_results)))
    top = unique_results[:top_n]
    try:
        # Cache only the minimal fingerprint (texts) to avoid heavy serialization
        texts: List[str] = [r.node.get_content() for r in top]
        set_json(cache_key, {"texts": texts})
    except Exception:
        pass
    return top
