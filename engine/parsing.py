import os
from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SimpleFileNodeParser


def parse_contract(file_path: str):
    """
    Parses a contract PDF into nodes using default LlamaIndex metadata.

    Args:
        file_path (str): Path to the contract file.

    Returns:
        list: Parsed nodes with default metadata.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ File not found: {file_path}")

    print("📥 Loading contract document...")
    reader = SimpleDirectoryReader(input_files=[file_path])
    documents = reader.load_data()

    if not documents:
        raise ValueError("❌ No document data found.")

    print("✅ Contract document loaded successfully.")
    
    parser = SimpleFileNodeParser()
    nodes = parser.get_nodes_from_documents(documents)

    print(f"✅ Contract parsed into {len(nodes)} nodes.")
    return nodes


def extract_metadata(nodes):
    """
    Extracts and aggregates metadata from parsed nodes.

    Args:
        nodes (list): List of parsed nodes.

    Returns:
        dict: Dictionary with metadata fields and values.
    """
    metadata = {}
    for node in nodes:
        for key, value in node.metadata.items():
            metadata.setdefault(key, []).append(value)
    return metadata


# Example usage
"""if __name__ == "__main__":
    nodes = parse_contract("../data/contracts/sample.pdf")
    for node in nodes:
        print(f"\nNode content:\n{node.get_content()}")
        print(f"Node metadata:\n{node.metadata}")
"""