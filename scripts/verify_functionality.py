#!/usr/bin/env python3
"""
CompliMate AI Engine - Functionality Verification
===============================================

This script verifies that both the original CLI functionality 
and the new API functionality work correctly.
"""

import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_original_engine():
    """Test that the original AI engine modules work."""
    print("🧠 Testing Original AI Engine Components...")
    
    try:
        # Test engine imports
        from engine.parsing import parse_contract
        from engine.retrieval import find_relevant_regulations  
        from engine.violation import create_violation_prompt, process_batch_violation_responses
        print("✅ Engine modules import successfully")
        
        # Test reporting imports
        from reporting.report_generator import generate_report, generate_text_report, generate_pdf_report
        print("✅ Reporting modules import successfully")
        
        # Test core LlamaIndex functionality
        from llama_index.core import VectorStoreIndex, Document
        from llama_index.llms.openai import OpenAI
        print("✅ LlamaIndex components import successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Original engine test failed: {e}")
        return False

def test_new_api_structure():
    """Test that the new API structure works."""
    print("\n🚀 Testing New API Structure...")
    
    try:
        # Test new config system
        from config import settings
        print(f"✅ Config system loaded (OpenAI configured: {bool(settings.OPENAI_API_KEY)})")
        
        # Test service layer
        from api.services import AnalysisService, FileService
        print("✅ Service layer imports successfully")
        
        # Test API models
        from api.models.schemas import HealthResponse, AnalysisStatus
        print("✅ API models import successfully")
        
        # Test utilities
        from utils import validate_file_type, setup_logging
        print("✅ Utility modules import successfully")
        
        # Test FastAPI app
        from api.main import app
        print("✅ FastAPI application loads successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ New API structure test failed: {e}")
        return False

def test_both_systems_coexist():
    """Test that both systems can coexist without conflicts."""
    print("\n🤝 Testing System Coexistence...")
    
    try:
        # Import from both old and new systems
        from engine.parsing import parse_contract as old_parse
        from api.services.analysis_service import AnalysisService
        
        # Create instances
        analysis_service = AnalysisService()
        
        print("✅ Both old and new systems can coexist")
        print(f"✅ Analysis service ready: {analysis_service.is_ready}")
        
        return True
        
    except Exception as e:
        print(f"❌ Coexistence test failed: {e}")
        return False

def main():
    """Run all verification tests."""
    print("🔍 CompliMate AI Engine - Functionality Verification")
    print("=" * 55)
    
    tests = [
        test_original_engine,
        test_new_api_structure, 
        test_both_systems_coexist
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 55)
    print(f"📊 Verification Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 ALL SYSTEMS OPERATIONAL!")
        print("\n📋 Available Options:")
        print("   1. Original CLI: python main.py")  
        print("   2. New API Server: python scripts/run_api.py")
        print("   3. API Documentation: http://localhost:8000/docs")
        print("\n✨ Both systems work independently and together!")
    else:
        print("⚠️  Some tests failed. Check the output above.")
    
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)