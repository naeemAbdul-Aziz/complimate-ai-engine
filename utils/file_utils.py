# utils/file_utils.py
"""
File handling utilities for CompliMate AI Engine
==============================================

This module contains utility functions for file operations,
validation, and management.
"""

import os
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class FileValidationError(Exception):
    """Custom exception for file validation errors."""
    pass


def validate_file_type(filename: str, allowed_extensions: tuple = ('.pdf', '.txt', '.docx')) -> bool:
    """
    Validate if file has an allowed extension.
    
    Args:
        filename: Name of the file to validate
        allowed_extensions: Tuple of allowed file extensions
        
    Returns:
        True if file type is allowed
        
    Raises:
        FileValidationError: If file type is not allowed
    """
    if not filename:
        raise FileValidationError("Filename cannot be empty")
    
    file_extension = Path(filename).suffix.lower()
    if file_extension not in allowed_extensions:
        raise FileValidationError(
            f"File type '{file_extension}' not allowed. "
            f"Allowed types: {', '.join(allowed_extensions)}"
        )
    
    return True


def validate_file_size(file_path: str, max_size_mb: int = 50) -> bool:
    """
    Validate file size.
    
    Args:
        file_path: Path to the file
        max_size_mb: Maximum allowed file size in MB
        
    Returns:
        True if file size is within limits
        
    Raises:
        FileValidationError: If file is too large
    """
    if not os.path.exists(file_path):
        raise FileValidationError(f"File does not exist: {file_path}")
    
    file_size = os.path.getsize(file_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise FileValidationError(
            f"File size ({file_size / 1024 / 1024:.2f} MB) "
            f"exceeds maximum allowed size ({max_size_mb} MB)"
        )
    
    return True


def generate_unique_filename(original_filename: str) -> Tuple[str, str]:
    """
    Generate a unique filename while preserving the original extension.
    
    Args:
        original_filename: Original filename
        
    Returns:
        Tuple of (unique_id, unique_filename)
    """
    file_id = str(uuid.uuid4())
    file_extension = Path(original_filename).suffix
    unique_filename = f"{file_id}{file_extension}"
    
    return file_id, unique_filename


def safe_file_write(content: bytes, file_path: str) -> None:
    """
    Safely write content to a file with error handling.
    
    Args:
        content: File content as bytes
        file_path: Destination file path
        
    Raises:
        IOError: If file write fails
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to temporary file first, then move to final location
        temp_path = f"{file_path}.tmp"
        
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # Atomic move to final location
        shutil.move(temp_path, file_path)
        
        logger.info(f"File written successfully: {file_path}")
        
    except Exception as e:
        # Clean up temporary file if it exists
        if os.path.exists(f"{file_path}.tmp"):
            os.remove(f"{file_path}.tmp")
        
        logger.error(f"Failed to write file {file_path}: {e}")
        raise IOError(f"Failed to write file: {e}")


def cleanup_old_files(directory: str, max_age_hours: int = 24) -> int:
    """
    Clean up old files from a directory.
    
    Args:
        directory: Directory to clean up
        max_age_hours: Maximum age of files to keep (in hours)
        
    Returns:
        Number of files deleted
    """
    if not os.path.exists(directory):
        return 0
    
    import time
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    
    try:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(f"Deleted old file: {file_path}")
        
        logger.info(f"Cleanup completed: {deleted_count} files deleted from {directory}")
        
    except Exception as e:
        logger.error(f"Error during cleanup of {directory}: {e}")
    
    return deleted_count


def get_file_info(file_path: str) -> dict:
    """
    Get detailed information about a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    stat = os.stat(file_path)
    
    return {
        "path": file_path,
        "filename": os.path.basename(file_path),
        "size": stat.st_size,
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
        "created": stat.st_ctime,
        "modified": stat.st_mtime,
        "extension": Path(file_path).suffix,
        "is_readable": os.access(file_path, os.R_OK),
        "is_writable": os.access(file_path, os.W_OK)
    }


def ensure_directory_exists(directory: str) -> None:
    """
    Ensure that a directory exists, create it if it doesn't.
    
    Args:
        directory: Directory path to ensure exists
    """
    try:
        os.makedirs(directory, exist_ok=True)
        logger.debug(f"Directory ensured: {directory}")
    except Exception as e:
        logger.error(f"Failed to ensure directory {directory}: {e}")


def find_files(directory: str, pattern: str) -> List[str]:
    """
    Find files matching a pattern in a directory.
    
    Args:
        directory: Directory to search
        pattern: File pattern to match (glob style)
        
    Returns:
        List of matching file paths
    """
    from glob import glob
    
    if not os.path.exists(directory):
        return []
    
    search_pattern = os.path.join(directory, pattern)
    return glob(search_pattern)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing invalid characters and normalizing spaces.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    
    # Remove extension if present
    name = Path(filename).stem
    
    # Replace invalid characters with underscores
    # Allow alphanumeric, hyphens, underscores, and spaces
    clean_name = re.sub(r'[^\w\s-]', '', name)
    
    # Replace multiple spaces with single underscore
    clean_name = re.sub(r'\s+', '_', clean_name)
    
    # Replace multiple underscores with single underscore
    clean_name = re.sub(r'_+', '_', clean_name)
    
    # Strip leading/trailing underscores
    clean_name = clean_name.strip('_')
    
    return clean_name


def generate_report_filename(contract_name: str, report_type: str = "pdf") -> str:
    """
    Generate a branded, descriptive report filename.
    
    Format: CompliMate_Analysis_{Clean_Contract_Name}.{ext}
    
    Args:
        contract_name: Original contract filename
        report_type: Extension (pdf, json, txt)
        
    Returns:
        Formatted filename
    """
    from datetime import datetime
    
    clean_name = sanitize_filename(contract_name)
    
    # Ensure report_type doesn't have a dot
    ext = report_type.lstrip('.')
    
    return f"CompliMate_Analysis_{clean_name}.{ext}"