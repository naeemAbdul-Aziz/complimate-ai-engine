#!/usr/bin/env python3
"""
Test script to verify that persistent storage is working correctly.
"""

import sys
import asyncio
from pathlib import Path

# Add the current directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from engine.regulation_manager import RegulationManager
from config.settings import settings

async def test_persistent_storage():
    """Test that persistent storage is working correctly."""
    print("=== Testing Persistent Storage ===")
    print(f"Vector store directory: {settings.VECTOR_STORE_DIR}")
    print(f"Expected ChromaDB file: {settings.VECTOR_STORE_DIR / 'chroma.sqlite3'}")
    print()
    
    # Initialize regulation manager
    print("1. Initializing RegulationManager...")
    manager = RegulationManager()
    
    # Check if using persistent storage
    print(f"2. Storage type: {'Persistent' if manager.using_persistent_storage else 'In-Memory'}")
    
    if manager.using_persistent_storage:
        print("✅ Successfully using persistent storage!")
        
        # Check if ChromaDB file exists
        chroma_file = settings.VECTOR_STORE_DIR / "chroma.sqlite3"
        if chroma_file.exists():
            print(f"✅ ChromaDB file exists: {chroma_file}")
            print(f"   File size: {chroma_file.stat().st_size} bytes")
        else:
            print("⚠️  ChromaDB file not found yet (will be created when data is indexed)")
            
    else:
        print("❌ Still using in-memory storage")
        print("   This means there might still be an issue with ChromaDB initialization")
    
    # Test indexing
    print("\n3. Testing regulation indexing...")
    try:
        result = manager.rebuild_index()
        print(f"   Indexed {result['files_processed']} files")
        print(f"   Total chunks: {result['total_chunks']}")
        
        # Check ChromaDB file after indexing
        if manager.using_persistent_storage:
            chroma_file = settings.VECTOR_STORE_DIR / "chroma.sqlite3"
            if chroma_file.exists():
                print(f"✅ ChromaDB file created: {chroma_file}")
                print(f"   File size after indexing: {chroma_file.stat().st_size} bytes")
            
    except Exception as e:
        print(f"❌ Error during indexing: {e}")
    
    # Get regulations info
    print("\n4. Regulation information:")
    info = manager.get_regulations_info()
    print(f"   Total regulations: {info['total_regulations']}")
    print(f"   Storage type: {info['storage_type']}")
    print(f"   Categories: {info['categories']}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_persistent_storage())