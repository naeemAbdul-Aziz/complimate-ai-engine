# Rebuild the regulations vector index for the current provider (Chroma or Pinecone)
# Usage (PowerShell):
#   $env:OPENAI_API_KEY='...'
#   # Optional: switch provider
#   # $env:VECTOR_DB_PROVIDER='pinecone'
#   # $env:PINECONE_API_KEY='...'
#   # $env:PINECONE_REGION='us-east-1'
#   # $env:PINECONE_CLOUD='aws'
#   C:/Users/naeemaziz/Desktop/complimate-ai-engine/venv/Scripts/python.exe scripts/rebuild_regulations_index.py

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.regulation_manager import RegulationManager

if __name__ == "__main__":
    clear = "--clear" in sys.argv
    mgr = RegulationManager()
    if clear:
        print("Clearing vector store and metadata...")
        mgr.force_clear_vector_store()
    result = mgr.rebuild_index(force=True)
    print("Rebuild result:")
    print(result)
