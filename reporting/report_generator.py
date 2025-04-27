import json
from fpdf import FPDF

def generate_report(report_data, output_file="analysis_report.json"):
    """
    Generates a structured JSON report of the contract analysis.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output JSON file path.
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=4, ensure_ascii=False)
        print(f"✅ JSON report successfully generated at {output_file}")
    except Exception as e:
        print(f"❌ Error generating JSON report: {e}")

def create_summary(report_data):
    """
    Creates a text summary from the report data.

    Args:
        report_data (dict): A dictionary containing the analysis results.

    Returns:
        str: A formatted summary string.
    """
    summary = ""
    contract_name = report_data.get('contract_name', 'Unknown Contract')

    if "violations" in report_data and report_data["violations"]:
        summary += f"Contract Name: {contract_name}\n"
        summary += f"Total Violations Found: {len(report_data['violations'])}\n\n"
        summary += "Detailed Violations:\n"
        for idx, violation in enumerate(report_data["violations"], start=1):
            summary += f"  {idx}. Type: {violation['type']}\n"
            summary += f"     Description: {violation['description']}\n"
            summary += f"     Contract Snippet: {violation['contract_snippet']}\n"
            summary += f"     Regulation Snippet: {violation['regulation_snippet']}\n"
            summary += "\n"
    else:
        summary = f"Contract Name: {contract_name}\nNo violations found."

    return summary

def generate_text_report(report_data, output_file="analysis_report.txt"):
    """
    Generates a human-readable text report of the contract analysis.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output text file path.
    """
    summary = create_summary(report_data)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)
        print(f"✅ Text report successfully generated at {output_file}")
    except Exception as e:
        print(f"❌ Error generating text report: {e}")

def generate_pdf_report(report_data, output_file="analysis_report.pdf"):
    """
    Generates a human-readable PDF report of the contract analysis.

    Args:
        report_data (dict): A dictionary containing the analysis results.
        output_file (str, optional): The output PDF file path.
    """
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        summary = create_summary(report_data)
        for line in summary.split("\n"):
            pdf.multi_cell(0, 10, line)
        
        pdf.output(output_file)
        print(f"✅ PDF report successfully generated at {output_file}")
    except Exception as e:
        print(f"❌ Error generating PDF report: {e}")
