# report_generator.py
import json
import logging
import datetime
import os
from fpdf import FPDF

# Configure logging for this module
logger = logging.getLogger(__name__)

# CompliMate brand colors
SEVERITY_COLORS = {
    "High": (153, 27, 27),       # Deep Red
    "Medium": (217, 119, 6),     # Orange-Gold
    "Low": (34, 197, 94),        # Soft Green
    "N/A": (148, 163, 184),      # Muted Gray
    "Uncategorized": (148, 163, 184),
    "Potential Compliance Issue (Parsing Failed)": (148, 163, 184),
}
DEFAULT_COLOR = (0, 0, 0)

BRAND_GREEN = (0, 100, 0)
BRAND_GOLD = (255, 215, 0)
BRAND_LIGHT_GRAY = (248, 248, 248)


class PDF(FPDF):
    def __init__(self, contract_name="N/A", regulation_file="N/A", **kwargs):
        super().__init__(**kwargs)
        self.contract_name = contract_name
        self.regulation_file = regulation_file
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_fill_color(*BRAND_GREEN)
        self.rect(0, 0, 210, 12, 'F')
        self.set_font('Arial', 'B', 11)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 5, f'Compliance Report: {self.contract_name}', 0, 1, 'C')
        self.set_text_color(*DEFAULT_COLOR)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        footer_text = f'Regulation: {os.path.basename(self.regulation_file)} | Page {self.page_no()}/{{nb}}'
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, footer_text, 0, 0, 'C')
        self.set_text_color(*DEFAULT_COLOR)

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 13)
        self.set_text_color(*BRAND_GREEN)
        self.cell(0, 10, title, 0, 1, 'L')
        self.set_text_color(*DEFAULT_COLOR)
        self.ln(2)

    def chapter_body(self, text, font_style='', font_size=11):
        self.set_font('Arial', font_style, font_size)
        self.multi_cell(0, 6, text)
        self.ln()

    def add_violation(self, index, violation):
        self.set_font('Arial', 'B', 11)
        severity = violation.get('severity', 'N/A')
        category = violation.get('category', 'Uncategorized')
        type = violation.get('type', 'Potential Compliance Issue')  # Get the type
        color = SEVERITY_COLORS.get(severity, DEFAULT_COLOR)

        self.set_text_color(*color)
        if type == "Universal Clause Issue":
            self.cell(0, 6, f"{index}. [Universal Clause] {violation.get('description', 'N/A')}", 0, 1)  # Different format
        else:
            self.cell(0, 6, f"{index}. [{severity}] {category}", 0, 1)  # Original format
        self.set_text_color(*DEFAULT_COLOR)

        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, f"   Issue: {violation.get('description', 'N/A')}")
        if type != "Universal Clause Issue":
            self.multi_cell(0, 5, f"   Regulation Ref: {violation.get('regulation_ref', 'N/A')}")  # Only for regulation issues
        self.ln(3)



# JSON + Text reports unchanged (kept for completeness)
def generate_report(report_data, output_file="analysis_report.json"):
    logger.info(f"Generating JSON report: {output_file}")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False)
        logger.info(f"JSON report successfully generated: {output_file}")
    except Exception as e:
        logger.exception(f"Error generating JSON report {output_file}: {e}")


def generate_text_report(report_data, output_file="analysis_report.txt"):
    logger.info(f"Generating text report: {output_file}")
    summary = ""
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        violations = report_data.get('violations', [])
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        summary += f"Compliance Analysis Report\n==========================\n"
        summary += f"Contract: {contract_name}\n"
        summary += f"Regulation: {regulation_file}\n"
        summary += f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"Prompts Sent: {total_prompts} | Successful LLM Responses: {successful_responses}\n"
        summary += f"Potential Issues Found: {len(violations)}\n\n"

        regulation_violations = [v for v in violations if v.get('type') == 'Potential Compliance Issue']
        universal_clause_issues = [v for v in violations if v.get('type') == 'Universal Clause Issue']

        summary += f"Potential Regulatory Compliance Issues Found: {len(regulation_violations)}\n"
        summary += f"Universal Clause Issues Found: {len(universal_clause_issues)}\n\n"

        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0, "Uncategorized": 0}
        for v in regulation_violations:  # Only count severity for regulation violations
            severity = v.get('severity', 'N/A')
            if severity in severity_counts:
                severity_counts[severity] += 1
            else:
                severity_counts["Uncategorized"] += 1

        summary += f"Regulatory Issues by Severity:\n"
        for sev, count in severity_counts.items():
            summary += f"  {sev}: {count}\n"

        summary += "\nDetailed Regulatory Compliance Issues:\n--------------------------------------\n"
        if regulation_violations:
            for idx, violation in enumerate(regulation_violations, start=1):
                summary += f"{idx}. [{violation.get('severity', 'N/A')}] {violation.get('category', 'Uncategorized')}\n"
                summary += f"   Issue: {violation.get('description', 'N/A')}\n"
                summary += f"   Regulation Ref: {violation.get('regulation_ref', 'N/A')}\n\n"
        else:
            summary += "No potential regulatory compliance issues identified.\n"

        summary += "\nUniversal Clause Issues:\n--------------------------\n"
        if universal_clause_issues:
            for idx, violation in enumerate(universal_clause_issues, start=1):
                summary += f"{idx}. [Universal Clause] {violation.get('description', 'N/A')}\n"
                summary += f"   Issue: {violation.get('description', 'N/A')}\n\n"
        else:
            summary += "No universal clause issues identified.\n"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)
        logger.info(f"Text report successfully generated: {output_file}")
    except Exception as e:
        logger.exception(f"Error generating text report {output_file}: {e}")


def generate_pdf_report(report_data, output_file="analysis_report.pdf"):
    logger.info(f"Generating PDF report: {output_file}")
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        violations = report_data.get('violations', [])
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        pdf = PDF(contract_name=contract_name, regulation_file=regulation_file)
        pdf.alias_nb_pages()
        pdf.add_page()

        pdf.set_font("Arial", 'B', 18)
        pdf.set_text_color(*BRAND_GREEN)
        pdf.cell(0, 20, "Contract Compliance Analysis Report", 0, 1, 'C')
        pdf.set_text_color(*DEFAULT_COLOR)
        pdf.ln(4)
        pdf.set_font("Arial", '', 12)
        pdf.cell(0, 10, f"Contract: {contract_name}", 0, 1, 'C')
        pdf.cell(0, 10, f"Regulation Analyzed: {os.path.basename(regulation_file)}", 0, 1, 'C')
        pdf.cell(0, 10, f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 1, 'C')
        pdf.ln(10)

        pdf.chapter_title("Executive Summary")
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, f"Total potential compliance issues identified: {len(violations)}")

        regulation_violations = [v for v in violations if v.get('type') == 'Potential Compliance Issue']
        universal_clause_issues = [v for v in violations if v.get('type') == 'Universal Clause Issue']

        pdf.ln(2)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, "Regulatory Compliance Issues by Severity:", 0, 1)
        pdf.set_font('Arial', '', 11)
        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0, "Uncategorized": 0}
        for v in regulation_violations:  # Only count severity for regulation violations
            sev = v.get('severity', 'N/A')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        for severity, count in severity_counts.items():
            if count > 0:
                pdf.set_text_color(*SEVERITY_COLORS.get(severity, DEFAULT_COLOR))
                pdf.cell(20)
                pdf.cell(0, 5, f"- {severity}: {count}", 0, 1)
        pdf.set_text_color(*DEFAULT_COLOR)
        pdf.ln(5)

        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, "Universal Clause Issues:", 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.cell(20)
        pdf.cell(0, 5, f"- Total: {len(universal_clause_issues)}", 0, 1)

        pdf.add_page()
        pdf.chapter_title("Detailed Regulatory Compliance Issues")
        if regulation_violations:
            for idx, violation in enumerate(regulation_violations, start=1):
                pdf.add_violation(idx, violation)
        else:
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 5, "No potential regulatory compliance issues identified during the analysis.")

        pdf.add_page()
        pdf.chapter_title("Universal Clause Issues")
        if universal_clause_issues:
            for idx, violation in enumerate(universal_clause_issues, start=1):
                pdf.add_violation(idx, violation)
        else:
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 5, "No universal clause issues identified during the analysis.")

        pdf.output(output_file, "F")
        logger.info(f"PDF report successfully generated: {output_file}")
    except ImportError:
        logger.error("FPDF library not found. Cannot generate PDF report. Install with 'pip install fpdf'")
    except Exception as e:
        logger.exception(f"Error generating PDF report {output_file}: {e}")
