# api/services/file_service.py
"""
File service for CompliMate AI Engine
===================================

This module handles file upload, validation, and management.
"""

import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import UploadFile

from config import settings
from utils import (
    validate_file_type, 
    validate_file_size, 
    generate_unique_filename,
    safe_file_write,
    get_file_info,
    LoggerMixin,
    FileValidationError
)


class FileService(LoggerMixin):
    """Service class for handling file operations."""
    
    def __init__(self):
        self.uploaded_files: Dict[str, Dict[str, Any]] = {}
        # Ensure upload directory exists
        settings.UPLOADS_DIR.mkdir(exist_ok=True, parents=True)
    
    async def upload_file(self, file: UploadFile) -> Dict[str, Any]:
        """
        Upload and validate a contract file.
        
        Args:
            file: FastAPI UploadFile object
            
        Returns:
            Dictionary with upload information
            
        Raises:
            FileValidationError: If file validation fails
        """
        try:
            # Validate filename exists
            if not file.filename:
                raise FileValidationError("No filename provided")
            
            # Validate file type
            validate_file_type(file.filename, settings.ALLOWED_FILE_EXTENSIONS)
            
            # Generate unique filename
            file_id, unique_filename = generate_unique_filename(file.filename)
            file_path = settings.UPLOADS_DIR / unique_filename
            
            # Read and save file content
            content = await file.read()
            safe_file_write(content, str(file_path))
            
            # Validate file size after writing
            validate_file_size(str(file_path), settings.MAX_FILE_SIZE_MB)
            
            # Get file information
            file_info = get_file_info(str(file_path))
            
            # Store file record
            upload_record = {
                "file_id": file_id,
                "original_filename": file.filename,
                "stored_filename": unique_filename,
                "file_path": str(file_path),
                "content_type": file.content_type,
                "file_size": file_info["size"],
                "uploaded_at": file_info["created"]
            }
            
            self.uploaded_files[file_id] = upload_record
            
            self.logger.info(f"File uploaded successfully: {file.filename} -> {file_id}")
            
            return {
                "message": "File uploaded successfully",
                "filename": file.filename,
                "file_id": file_id,
                "file_path": str(file_path),
                "file_size": file_info["size"]
            }
            
        except FileValidationError:
            raise
        except Exception as e:
            self.logger.error(f"Error uploading file {file.filename}: {e}")
            raise FileValidationError(f"Upload failed: {e}")
    
    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an uploaded file.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            File information dictionary or None if not found
        """
        return self.uploaded_files.get(file_id)
    
    def get_file_path(self, file_id: str) -> Optional[str]:
        """
        Get the file path for an uploaded file.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            File path or None if not found
        """
        file_info = self.uploaded_files.get(file_id)
        if file_info and os.path.exists(file_info["file_path"]):
            return file_info["file_path"]
        return None
    
    def delete_file(self, file_id: str) -> bool:
        """
        Delete an uploaded file.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            True if file was deleted successfully
        """
        try:
            file_info = self.uploaded_files.get(file_id)
            if not file_info:
                return False
            
            file_path = file_info["file_path"]
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.info(f"Deleted file: {file_path}")
            
            # Remove from records
            del self.uploaded_files[file_id]
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error deleting file {file_id}: {e}")
            return False
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up old uploaded files.
        
        Args:
            max_age_hours: Maximum age of files to keep (in hours)
            
        Returns:
            Number of files cleaned up
        """
        import time
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned_count = 0
        
        files_to_remove = []
        
        for file_id, file_info in self.uploaded_files.items():
            file_age = current_time - file_info["uploaded_at"]
            
            if file_age > max_age_seconds:
                files_to_remove.append(file_id)
        
        for file_id in files_to_remove:
            if self.delete_file(file_id):
                cleaned_count += 1
        
        self.logger.info(f"Cleaned up {cleaned_count} old uploaded files")
        return cleaned_count
    
    def list_uploaded_files(self) -> Dict[str, Dict[str, Any]]:
        """
        Get list of all uploaded files.
        
        Returns:
            Dictionary of file records
        """
        return self.uploaded_files.copy()
    
    def validate_file_exists(self, file_id: str) -> bool:
        """
        Validate that a file exists both in records and on disk.
        
        Args:
            file_id: Unique file identifier
            
        Returns:
            True if file exists
        """
        file_info = self.uploaded_files.get(file_id)
        if not file_info:
            return False
        
        return os.path.exists(file_info["file_path"])