# tests/unit/test_file_service.py
"""
Unit tests for File Service
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from api.services.file_service import FileService
from utils.file_utils import FileValidationError


class TestFileService:
    """Test cases for FileService class."""
    
    def setup_method(self):
        """Set up test fixtures before each test method."""
        self.file_service = FileService()
    
    def test_file_service_initialization(self):
        """Test FileService initialization."""
        assert self.file_service is not None
        assert isinstance(self.file_service.uploaded_files, dict)
    
    @pytest.mark.asyncio
    async def test_upload_valid_file(self, sample_pdf_file):
        """Test uploading a valid PDF file."""
        # Mock UploadFile
        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"
        
        with open(sample_pdf_file, "rb") as f:
            mock_file.read.return_value = f.read()
        
        with patch('api.services.file_service.settings') as mock_settings:
            mock_settings.UPLOADS_DIR = Path(tempfile.mkdtemp())
            mock_settings.ALLOWED_FILE_EXTENSIONS = ('.pdf', '.txt', '.docx')
            mock_settings.MAX_FILE_SIZE_MB = 50
            
            result = await self.file_service.upload_file(mock_file)
            
            assert result["message"] == "File uploaded successfully"
            assert result["filename"] == "test.pdf"
            assert "file_id" in result
            assert "file_path" in result
    
    @pytest.mark.asyncio 
    async def test_upload_invalid_file_type(self):
        """Test uploading an invalid file type."""
        mock_file = Mock()
        mock_file.filename = "test.exe"
        mock_file.content_type = "application/exe"
        mock_file.read.return_value = b"fake content"
        
        with pytest.raises(FileValidationError):
            await self.file_service.upload_file(mock_file)
    
    @pytest.mark.asyncio
    async def test_upload_no_filename(self):
        """Test uploading file with no filename."""
        mock_file = Mock()
        mock_file.filename = None
        
        with pytest.raises(FileValidationError):
            await self.file_service.upload_file(mock_file)
    
    def test_get_file_info_existing(self):
        """Test getting file info for existing file."""
        # Add a test file record
        test_file_id = "test-123"
        test_record = {
            "file_id": test_file_id,
            "original_filename": "test.pdf",
            "stored_filename": "test-123.pdf",
            "file_path": "/uploads/test-123.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
            "uploaded_at": 1234567890
        }
        
        self.file_service.uploaded_files[test_file_id] = test_record
        
        result = self.file_service.get_file_info(test_file_id)
        assert result == test_record
    
    def test_get_file_info_nonexistent(self):
        """Test getting file info for nonexistent file."""
        result = self.file_service.get_file_info("nonexistent")
        assert result is None
    
    def test_validate_file_exists_false(self):
        """Test validating nonexistent file."""
        result = self.file_service.validate_file_exists("nonexistent")
        assert result is False