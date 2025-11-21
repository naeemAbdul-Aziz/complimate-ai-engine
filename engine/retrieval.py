import logging
from typing import List

from llama_index.core.schema import QueryBundle
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.retrievers.bm25 import BM25Retriever

from utils.cache import get_json, set_json, key_hash

logger = logging.getLogger(__name__)


class RetrievalManager:
    """Manages retrieval components to avoid expensive re-initialization."""
    
    def __init__(self, regulation_index):
        self.regulation_index = regulation_index
        self._bm25_retriever = None
        
    def get_bm25_retriever(self):
        """Get or create BM25 retriever (reusable)."""
        if self._bm25_retriever is None:
            logger.info("Initializing BM25Retriever (lazy load)...")
            self._bm25_retriever = BM25Retriever.from_defaults(index=self.regulation_index)
        return self._bm25_retriever

# Global manager instance (lazy initialized)
_retrieval_manager = None

def get_retrieval_manager(index) -> RetrievalManager:
    global _retrieval_manager
    if _retrieval_manager is None or _retrieval_manager.regulation_index != index:
        _retrieval_manager = RetrievalManager(index)
    return _retrieval_manager


def find_relevant_regulations(contract_node, regulation_index, top_n=5):
    """
    Finds relevant regulations for a given contract node using hybrid search.
    
    Optimized with caching and reusable components.
    """
    content = contract_node.get_content()
    # Include top_n in hash to avoid returning fewer results than requested if cached
    cache_key = f"retrieval_v2:{key_hash({'content': content, 'top_n': top_n})}"

    cached_data = get_json(cache_key)
    if cached_data:
        logger.info("Retrieval cache hit. Returning %d cached results.", len(cached_data))
        # Reconstruct NodeWithScore objects from cached dicts
        results = []
        try:
            from llama_index.core.schema import NodeWithScore, TextNode
            for item in cached_data:
                node = TextNode(
                    text=item['text'],
                    metadata=item.get('metadata', {}),
                    id_=item.get('node_id')
                )
                results.append(NodeWithScore(node=node, score=item.get('score', 0.0)))
            return results
        except Exception as e:
            logger.warning(f"Failed to rehydrate cached results: {e}. Proceeding with fresh search.")
            # Fall through to fresh search

    # Get reusable manager
    manager = get_retrieval_manager(regulation_index)
    
    # 1. BM25 Search (Keyword)
    bm25_retriever = manager.get_bm25_retriever()
    query_bundle = QueryBundle(query_str=content)
    bm25_results = bm25_retriever.retrieve(query_bundle)
    logger.info("BM25 search results retrieved. Count: %d", len(bm25_results))

    # 2. Vector Search (Semantic)
    # Vector retriever is lightweight to init, but we could also cache it if needed
    vector_retriever = VectorIndexRetriever(index=regulation_index, similarity_top_k=top_n)
    vector_results = vector_retriever.retrieve(query_bundle)
    logger.info("Vector search results retrieved. Count: %d", len(vector_results))

    # 3. Hybrid Merge (RRF or simple score sort)
    # Simple merge: combine and deduplicate by content
    all_results = bm25_results + vector_results
    all_results.sort(key=lambda x: (x.score or 0.0), reverse=True)
    
    unique_results = []
    seen_texts = set()
    for result in all_results:
        # Use content hash for stricter deduplication than just string equality
        c_hash = key_hash(result.node.get_content())
        if c_hash not in seen_texts:
            unique_results.append(result)
            seen_texts.add(c_hash)

    top_results = unique_results[:top_n]
    logger.info("Returning top %d unique results.", len(top_results))
    
    # Cache the results (serialize to dicts)
    try:
        cache_payload = []
        for r in top_results:
            cache_payload.append({
                'text': r.node.get_content(),
                'metadata': r.node.metadata,
                'node_id': r.node.node_id,
                'score': r.score
            })
        set_json(cache_key, cache_payload, tier="retrieval")
    except Exception as e:
        logger.warning(f"Failed to cache retrieval results: {e}")
        
    return top_results
