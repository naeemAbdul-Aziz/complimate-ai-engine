from llama_index.core.schema import QueryBundle
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.retrievers.bm25 import BM25Retriever

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
    bm25_retriever = BM25Retriever.from_defaults(
        index=regulation_index, 
    )
    vector_retriever = VectorIndexRetriever(index=regulation_index, similarity_top_k=3)


    query_bundle = QueryBundle(query_str=contract_node.get_content())
    bm25_results = bm25_retriever.retrieve(query_bundle)
    print("✅ BM25 search results retrieved.")
    vector_results = vector_retriever.retrieve(query_bundle)
    print("✅ Vector search results retrieved.")
    print("✅ Hybrid search results retrieved.")


    all_results = bm25_results + vector_results
    all_results.sort(key=lambda x: x.score, reverse=True)
    unique_results = []
    seen_texts = set()
    for result in all_results:
        if result.node.get_content() not in seen_texts:
            unique_results.append(result)
            seen_texts.add(result.node.get_content())
    return unique_results[:3]

