import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from reporting.report_generator import generate_pdf_report
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_pdf_generation():
    """
    Verify PDF generation with multi-regulation support.
    """
    logger.info("Starting PDF verification...")
    
    # Mock data with multiple regulations
    report_data = {
        "contract_name": "Test_Contract_2024.pdf",
        "regulation_file": ["Petroleum_Regs_2023.pdf", "Environmental_Act_2020.pdf"],
        "violations": [
            {
                "section": "Section 12(a)",
                "text": "Failure to submit quarterly reports.",
                "severity": "High",
                "recommendation": "Submit reports immediately.",
                "regulation": "Petroleum_Regs_2023.pdf"
            },
            {
                "section": "Section 5(b)",
                "text": "Improper waste disposal.",
                "severity": "Critical",
                "recommendation": "Halt operations and fix disposal system.",
                "regulation": "Environmental_Act_2020.pdf"
            }
        ],
        "compliance_score": 75.5,
        "summary": "This is a test summary demonstrating multi-regulation support.",
        "analysis_date": datetime.now().isoformat()
    }
    
    output_file = "test_multi_reg_report.pdf"
    
    try:
        generate_pdf_report(report_data, output_file)
        logger.info(f"Successfully generated {output_file}")
        
        # Verify file exists and has content
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            logger.info("Verification PASSED: PDF file created and is not empty.")
        else:
            logger.error("Verification FAILED: PDF file not found or empty.")
            
    except Exception as e:
        logger.error(f"Verification FAILED: {e}")
        raise

if __name__ == "__main__":
    verify_pdf_generation()
