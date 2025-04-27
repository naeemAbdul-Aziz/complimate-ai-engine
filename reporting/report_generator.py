# reporting/report_generator.py
import json
import logging
import datetime
import os
from fpdf import FPDF

# Configure logging for this module
logger = logging.getLogger(__name__)

# Define severity colors (adjust RGB values as needed)
SEVERITY_COLORS = {
    "High": (255, 0, 0),      # Red
    "Medium": (255, 165, 0),  # Orange
    "Low": (255, 255, 0),     # Yellow
    "N/A": (200, 200, 200),   # Grey
    "Uncategorized": (200, 200, 200), # Grey
    "Potential Compliance Issue (Parsing Failed)": (200, 200, 200), # Grey
}
DEFAULT_COLOR = (0, 0, 0)     # Black


# Helper class for PDF generation with header/footer
class PDF(FPDF):
    def __init__(self, contract_name="N/A", regulation_file="N/A", **kwargs):
        super().__init__(**kwargs)
        self.contract_name = contract_name
        self.regulation_file = regulation_file
        self.set_auto_page_break(auto=True, margin=15) # Enable auto page break

    def header(self):
        self.set_font('Arial', 'B', 10)
        self.cell(0, 10, f'Compliance Analysis Report: {self.contract_name}', 0, 0, 'C')
        self.ln(10) # Line break

    def footer(self):
        self.set_y(-15) # Position 1.5 cm from bottom
        self.set_font('Arial', 'I', 8)
        # Add regulation file info and page number
        footer_text = f'Regulation: {os.path.basename(self.regulation_file)} | Page {self.page_no()}/{{nb}}'
        self.cell(0, 10, footer_text, 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(5) # Line break

    def chapter_body(self, text, font_style='', font_size=11):
        self.set_font('Arial', font_style, font_size)
        self.multi_cell(0, 5, text) # Use smaller line height (5)
        self.ln()

    def add_violation(self, index, violation):
        self.set_font('Arial', 'B', 11)
        severity = violation.get('severity', 'N/A')
        category = violation.get('category', 'Uncategorized')
        color = SEVERITY_COLORS.get(severity, DEFAULT_COLOR)

        # Print violation number and category with severity color
        self.set_text_color(*color)
        self.cell(0, 6, f"{index}. [{severity}] {category}", 0, 1)
        self.set_text_color(*DEFAULT_COLOR) # Reset color

        # Print details
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, f"   Issue: {violation.get('description', 'N/A')}")
        self.multi_cell(0, 5, f"   Regulation Ref: {violation.get('regulation_ref', 'N/A')}")
        # Optionally include snippets (can make PDF very long)
        # self.set_font('Arial', 'I', 9)
        # self.multi_cell(0, 4, f"   Contract Snippet: {violation.get('contract_snippet', 'N/A')}")
        # self.multi_cell(0, 4, f"   Regulation Snippet: {violation.get('regulation_snippet', 'N/A')}")
        self.ln(3) # Space after violation


def generate_report(report_data, output_file="analysis_report.json"):
    """
    Generates a structured JSON report of the contract analysis.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output JSON file path.
    """
    logger.info(f"Generating JSON report: {output_file}")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False)
        logger.info(f"JSON report successfully generated: {output_file}")
    except Exception as e:
        logger.exception(f"Error generating JSON report {output_file}: {e}")


def generate_text_report(report_data, output_file="analysis_report.txt"):
    """
    Generates a human-readable text report of the contract analysis.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output text file path.
    """
    logger.info(f"Generating text report: {output_file}")
    summary = ""
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        violations = report_data.get('violations', [])
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        # Header
        summary += f"Compliance Analysis Report\n"
        summary += f"==========================\n"
        summary += f"Contract: {contract_name}\n"
        summary += f"Regulation: {regulation_file}\n"
        summary += f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"Prompts Sent: {total_prompts} | Successful LLM Responses: {successful_responses}\n"
        summary += f"Potential Issues Found: {len(violations)}\n\n"

        # Summary by Severity
        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0, "Uncategorized": 0}
        for v in violations:
            severity = v.get('severity', 'N/A')
            if severity in severity_counts:
                severity_counts[severity] += 1
            else: # Handle unexpected severity values if necessary
                 severity_counts["Uncategorized"] +=1

        summary += f"Issues by Severity:\n"
        summary += f"  High:   {severity_counts['High']}\n"
        summary += f"  Medium: {severity_counts['Medium']}\n"
        summary += f"  Low:    {severity_counts['Low']}\n"
        summary += f"  N/A/Other: {severity_counts['N/A'] + severity_counts['Uncategorized']}\n\n"

        # Detailed Violations
        if violations:
            summary += "Detailed Issues:\n"
            summary += "----------------\n"
            for idx, violation in enumerate(violations, start=1):
                severity = violation.get('severity', 'N/A')
                category = violation.get('category', 'Uncategorized')
                reg_ref = violation.get('regulation_ref', 'N/A')
                desc = violation.get('description', 'N/A')

                summary += f"{idx}. [{severity}] {category}\n"
                summary += f"   Issue: {desc}\n"
                summary += f"   Regulation Ref: {reg_ref}\n"
                # Optionally add snippets
                # summary += f"   Contract Snippet: {violation.get('contract_snippet', 'N/A')}\n"
                # summary += f"   Regulation Snippet: {violation.get('regulation_snippet', 'N/A')}\n"
                summary += "\n"
        else:
            summary += "No potential compliance issues identified.\n"

        # Write file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)
        logger.info(f"Text report successfully generated: {output_file}")

    except Exception as e:
        logger.exception(f"Error generating text report {output_file}: {e}")


def generate_pdf_report(report_data, output_file="analysis_report.pdf"):
    """
    Generates an improved, investor-friendly PDF report using FPDF.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output PDF file path.
    """
    logger.info(f"Generating PDF report: {output_file}")
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        violations = report_data.get('violations', [])
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        pdf = PDF(contract_name=contract_name, regulation_file=regulation_file)
        pdf.alias_nb_pages() # Enable page numbering
        pdf.add_page()

        # Title Page (optional - simple version here)
        pdf.set_font("Arial", 'B', 18)
        pdf.cell(0, 20, "Contract Compliance Analysis Report", 0, 1, 'C')
        pdf.ln(10)
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"Contract: {contract_name}", 0, 1, 'C')
        pdf.cell(0, 10, f"Regulation Analyzed: {os.path.basename(regulation_file)}", 0, 1, 'C')
        pdf.cell(0, 10, f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'C')
        pdf.ln(10)

        # --- Executive Summary ---
        pdf.chapter_title("Executive Summary")
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, f"Total potential compliance issues identified: {len(violations)}")

        # Summary by Severity
        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0, "Uncategorized": 0, "Potential Compliance Issue (Parsing Failed)":0}
        for v in violations:
            severity = v.get('severity', 'N/A')
            if severity in severity_counts:
                severity_counts[severity] += 1
            else: # Handle unexpected severity values
                 severity_counts["Uncategorized"] +=1

        pdf.ln(2)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, "Issues by Severity:", 0, 1)
        pdf.set_font('Arial', '', 11)
        # Set colors for summary counts
        for severity, count in severity_counts.items():
            if count > 0: # Only show severities with counts
                 color = SEVERITY_COLORS.get(severity, DEFAULT_COLOR)
                 pdf.set_text_color(*color)
                 pdf.cell(20) # Indent
                 pdf.cell(0, 5, f"- {severity}: {count}", 0, 1)
        pdf.set_text_color(*DEFAULT_COLOR) # Reset color
        pdf.ln(5)

        # --- Detailed Findings ---
        pdf.add_page()
        pdf.chapter_title("Detailed Compliance Issues")

        if violations:
            for idx, violation in enumerate(violations, start=1):
                pdf.add_violation(idx, violation)
        else:
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 5, "No potential compliance issues identified during the analysis.")

        # Save the PDF
        pdf.output(output_file, "F")
        logger.info(f"PDF report successfully generated: {output_file}")

    except ImportError:
         logger.error("FPDF library not found. Cannot generate PDF report. Install with 'pip install fpdf'")
    except Exception as e:
        logger.exception(f"Error generating PDF report {output_file}: {e}")