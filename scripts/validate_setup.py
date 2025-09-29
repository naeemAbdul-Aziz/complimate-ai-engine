#!/usr/bin/env python3
"""
Setup and validation script for CompliMate AI Engine
===================================================

This script validates the installation and setup of the refactored codebase.
"""

import sys
import os
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def check_python_version():
    """Check if Python version is compatible."""
    print("🐍 Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required. Current version:", sys.version)
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def check_environment_file():
    """Check if .env file exists and has required variables."""
    print("\n🔧 Checking environment configuration...")
    env_file = Path(".env")
    
    if not env_file.exists():
        print("⚠️  .env file not found. Creating template...")
        template = """# CompliMate AI Engine Configuration
OPENAI_API_KEY=your_openai_key_here
ENVIRONMENT=development
LOG_LEVEL=INFO
API_PORT=8000
MAX_FILE_SIZE_MB=50
MAX_CONCURRENT_ANALYSES=5
"""
        env_file.write_text(template)
        print("📝 Template .env file created. Please update with your values.")
        return False
    
    # Check for required variables
    content = env_file.read_text()
    required_vars = ["OPENAI_API_KEY"]
    
    for var in required_vars:
        if f"{var}=" not in content:
            print(f"❌ Missing required environment variable: {var}")
            return False
    
    print("✅ Environment configuration looks good")
    return True

def check_directories():
    """Ensure all required directories exist."""
    print("\n📁 Checking directory structure...")
    
    required_dirs = [
        "api", "api/endpoints", "api/models", "api/services",
        "config", "engine", "reporting", "utils", "tests", "tests/unit", "tests/integration",
        "scripts", "data", "data/contracts", "data/regulations", "uploads", "reports"
    ]
    
    for directory in required_dirs:
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"📁 Creating missing directory: {directory}")
            dir_path.mkdir(parents=True, exist_ok=True)
        
    print("✅ Directory structure validated")
    return True

def check_imports():
    """Test if all modules can be imported."""
    print("\n📦 Testing module imports...")
    
    test_imports = [
        ("config", "settings"),
        ("utils", "file_utils"),
        ("utils", "logging_utils"),
        ("api.models", "schemas"),
        ("api.services", "AnalysisService"),
        ("api.services", "FileService"),
    ]
    
    for module, item in test_imports:
        try:
            exec(f"from {module} import {item}")
            print(f"✅ {module}.{item}")
        except ImportError as e:
            print(f"❌ Failed to import {module}.{item}: {e}")
            return False
    
    return True

def check_dependencies():
    """Check if required packages are installed."""
    print("\n📚 Checking dependencies...")
    
    try:
        import fastapi
        import uvicorn
        import openai
        import llama_index
        print("✅ Core dependencies installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("💡 Run: pip install -r requirements.txt")
        return False

def run_basic_api_test():
    """Test if the API can start up."""
    print("\n🚀 Testing API startup...")
    
    try:
        # Try to import the app
        from api.main import app
        print("✅ API application loads successfully")
        
        # Test with FastAPI test client
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        response = client.get("/health")
        if response.status_code == 200:
            print("✅ Health endpoint responds correctly")
            return True
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ API startup failed: {e}")
        return False

def main():
    """Run all validation checks."""
    print("🔍 CompliMate AI Engine - Setup Validation")
    print("=" * 50)
    
    checks = [
        check_python_version,
        check_environment_file,
        check_directories,
        check_dependencies,
        check_imports,
        run_basic_api_test,
    ]
    
    passed = 0
    total = len(checks)
    
    for check in checks:
        if check():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All checks passed! CompliMate is ready to go!")
        print("\n🚀 To start the API server:")
        print("   python scripts/run_api.py")
        print("\n📖 API Documentation:")
        print("   http://localhost:8000/docs")
    else:
        print("⚠️  Some checks failed. Please review the issues above.")
        print("💡 Check the documentation for troubleshooting help.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)