#!/usr/bin/env python3
"""
Regulation Ingestion Script
==========================

This script is responsible for "compiling" the regulation PDFs into a vector index.
It should be run:
1. During initial deployment.
2. Whenever new regulation files are added to `data/regulations`.
3. When the embedding model or chunking strategy changes.

Usage:
    python scripts/ingest_regulations.py [--force]
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import settings
from config.logger import configure_logging
from engine.regulation_manager import RegulationManager
import nltk

# Download necessary NLTK data for llama_index/langchain
try:
    nltk.download('stopwords', quiet=True)
    nltk.download('punkt', quiet=True)
except Exception as e:
    print(f"Warning: Failed to download NLTK data: {e}")

# Configure logging for the script
logger = logging.getLogger("complimate.ingestion")
configure_logging()

async def main():
    parser = argparse.ArgumentParser(description="Ingest regulations into the vector store.")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of all files, ignoring cache/hashes.")
    args = parser.parse_args()

    logger.info("=== Starting Regulation Ingestion ===")
    logger.info(f"Regulations Directory: {settings.REGULATIONS_DIR}")
    logger.info(f"Vector Store Provider: {settings.VECTOR_DB_PROVIDER}")
    logger.info(f"Force Rebuild: {args.force}")

    try:
        manager = RegulationManager()
        
        # Check if we have files to index
        files = manager.discover_regulation_files()
        if not files:
            logger.warning("No regulation files found! Please add PDFs to data/regulations.")
            return

        logger.info(f"Found {len(files)} regulation files.")
        
        # Run the rebuild process (synchronous)
        result = manager.rebuild_index(force=args.force)
        
        if result.get("status") == "completed":
            logger.info("=== Ingestion Complete Successfully ===")
            logger.info(f"Files Processed: {result.get('files_processed', 0)}")
            logger.info(f"Files Skipped: {result.get('files_skipped', 0)}")
            logger.info(f"Files Failed: {result.get('files_failed', 0)}")
            logger.info(f"Total Regulations: {result.get('total_regulations', 0)}")
            
            # Verify Pinecone Stats
            if settings.VECTOR_DB_PROVIDER == "pinecone":
                try:
                    from pinecone import Pinecone
                    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                    index = pc.Index(settings.PINECONE_INDEX_NAME)
                    stats = index.describe_index_stats()
                    logger.info(f"Pinecone Index Stats: {stats}")
                except Exception as e:
                    logger.error(f"Failed to fetch Pinecone stats: {e}")
        elif result.get("status") == "cooldown":
            logger.info("=== Ingestion Skipped ===")
            logger.info(f"Reason: Cooldown active")
        else:
            logger.error(f"=== Ingestion Failed ===\\nResult: {result}")
            sys.exit(1)

    except Exception as e:
        logger.exception(f"Fatal error during ingestion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
