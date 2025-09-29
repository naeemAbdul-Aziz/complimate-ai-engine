#!/usr/bin/env python3
"""
Script to reset and reinitialize the vector store properly.
This ensures we get persistent storage instead of in-memory fallback.
"""

import sys
import shutil
from pathlib import Path
import logging

# Add the current directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_vector_store():
    """Reset the vector store directory and metadata."""
    try:
        # Remove vector store directory if it exists
        if settings.VECTOR_STORE_DIR.exists():
            logger.info(f"Removing existing vector store directory: {settings.VECTOR_STORE_DIR}")
            try:
                shutil.rmtree(settings.VECTOR_STORE_DIR)
                logger.info("Vector store directory removed successfully")
            except PermissionError as e:
                logger.error(f"Permission error removing vector store: {e}")
                logger.info("Trying alternative approach: renaming corrupted files...")
                
                # Try to rename the corrupted files instead
                try:
                    import time
                    timestamp = int(time.time())
                    backup_dir = settings.VECTOR_STORE_DIR.parent / f"vector_store_backup_{timestamp}"
                    settings.VECTOR_STORE_DIR.rename(backup_dir)
                    logger.info(f"Moved corrupted vector store to: {backup_dir}")
                except Exception as rename_error:
                    logger.error(f"Failed to rename vector store: {rename_error}")
                    logger.info("Manual intervention required:")
                    logger.info("1. Stop all Python processes")
                    logger.info("2. Delete the vector_store directory manually")
                    logger.info("3. Run this script again")
                    return False
            except Exception as e:
                logger.error(f"Error removing vector store directory: {e}")
                return False
        
        # Remove metadata file if it exists
        metadata_file = settings.DATA_DIR / "regulations_metadata.json"
        if metadata_file.exists():
            logger.info(f"Removing metadata file: {metadata_file}")
            metadata_file.unlink()
        
        # Create fresh vector store directory
        settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created fresh vector store directory: {settings.VECTOR_STORE_DIR}")
        
        logger.info("Vector store reset completed successfully")
        logger.info("The next time you run the application, it will use persistent storage")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reset vector store: {e}")
        return False

if __name__ == "__main__":
    print("=== Vector Store Reset Script ===")
    print(f"Vector store directory: {settings.VECTOR_STORE_DIR}")
    print(f"Metadata file: {settings.DATA_DIR / 'regulations_metadata.json'}")
    print()
    
    confirmation = input("Are you sure you want to reset the vector store? This will remove all indexed data. (y/N): ")
    if confirmation.lower() in ['y', 'yes']:
        success = reset_vector_store()
        if success:
            print("\n✅ Vector store reset successfully!")
            print("You can now run your application and it will use persistent storage.")
        else:
            print("\n❌ Failed to reset vector store. Check the logs above.")
            sys.exit(1)
    else:
        print("Reset cancelled.")