#!/usr/bin/env python3
"""
CompliMate API Server Startup Script
====================================

This script starts the CompliMate FastAPI server for contract compliance analysis.

Usage:
    python run_api.py

The server will start on http://localhost:8000
API documentation will be available at http://localhost:8000/docs
"""

import sys
import os
from pathlib import Path
import uvicorn
import logging

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    print("🚀 Starting CompliMate API Server...")
    print("📊 API Documentation: http://localhost:8000/docs")
    print("🔍 Health Check: http://localhost:8000/health")
    print("💡 Press Ctrl+C to stop the server")
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info"
    )