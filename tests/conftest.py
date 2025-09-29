# tests/conftest.py
"""
Pytest configuration and fixtures for CompliMate tests
"""

import os
import tempfile
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Set test environment
os.environ["ENVIRONMENT"] = "testing"

from api.main import app
from config import settings


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_pdf_file(temp_dir):
    """Create a sample PDF file for testing."""
    pdf_path = temp_dir / "sample.pdf"
    # Create a minimal PDF content (for testing purposes)
    pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Sample Contract) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
301
%%EOF"""
    
    pdf_path.write_bytes(pdf_content)
    return pdf_path


@pytest.fixture
def mock_openai_key(monkeypatch):
    """Mock OpenAI API key for testing."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")


@pytest.fixture
def sample_contract_text():
    """Sample contract text for testing."""
    return """
    PETROLEUM SERVICES AGREEMENT
    
    This Agreement is made between:
    1. OILTECH GHANA LTD., a company incorporated under the laws of Ghana
    2. GHANA NATIONAL PETROLEUM CORPORATION
    
    The Contractor agrees to provide petroleum services in accordance with
    applicable laws and regulations including local content requirements.
    """


@pytest.fixture
def sample_violation():
    """Sample violation data for testing."""
    return {
        "description": "Contract does not specify local content requirements",
        "category": "Missing Obligation",
        "regulation_ref": "Regulation 33",
        "severity": "High",
        "type": "Potential Compliance Issue",
        "contract_node_id": "test-node-1",
        "regulation_node_id": "test-reg-1",
        "contract_snippet": "Sample contract text...",
        "regulation_snippet": "Sample regulation text..."
    }