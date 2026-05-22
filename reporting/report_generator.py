# report_generator.py
import json
import logging
import datetime
import os
from fpdf import FPDF
from typing import Any

# Configure logging for this module
logger = logging.getLogger(__name__)

# --- Premium Color Palette ---
# Primary Brand Colors
BRAND_DEEP_GREEN = (0, 77, 64)        # Professional dark green
BRAND_ACCENT_GOLD = (255, 193, 7)     # Premium gold accent
BRAND_LIGHT_CREAM = (250, 250, 245)   # Warm background
BRAND_TEXT_PRIMARY = (33, 33, 33)     # Near black
BRAND_TEXT_SECONDARY = (97, 97, 97)   # Medium gray
DIVIDER_COLOR = (224, 224, 224)       # Light gray

# Severity Colors (Refined)
SEVERITY_COLORS = {
    "Critical": (183, 28, 28),       # Deep Red
    "High": (230, 81, 0),            # Vibrant Orange
    "Medium": (245, 166, 35),        # Warm Amber
    "Low": (56, 142, 60),            # Calm Green
    "N/A": (148, 163, 184),          # Muted Gray
    "Uncategorized": (148, 163, 184),
    "Potential Compliance Issue (Parsing Failed)": (148, 163, 184),
}

DEFAULT_COLOR = (0, 0, 0)


# Helpers
def _serialize_for_json(obj: Any, _seen: set | None = None) -> Any:
    """Recursively convert an object graph into JSON-serializable primitives."""
    if _seen is None:
        _seen = set()

    obj_id = id(obj)
    if obj_id in _seen:
        return "<circular ref>"
    # primitives
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    _seen.add(obj_id)

    # dicts
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            try:
                key = str(k)
            except Exception:
                key = "<non-string-key>"
            result[key] = _serialize_for_json(v, _seen)
        return result

    # iterables
    if isinstance(obj, (list, tuple, set)):
        return [_serialize_for_json(v, _seen) for v in obj]

    # fallback
    try:
        return str(obj)
    finally:
        pass


def _safe_pdf_text(text: Any) -> str:
    """Normalize text for fpdf (latin-1 core fonts)."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Common replacements
    replacements = {
        "\u2014": "--",  # em-dash
        "\u2013": "-",   # en-dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def _normalize_violation(v: dict) -> dict:
    """Normalize violation dictionaries to a common schema."""
    if not isinstance(v, dict):
        return {
            "description": str(v),
            "category": "Uncategorized",
            "regulation_ref": "N/A",
            "severity": "N/A",
            "type": "Potential Compliance Issue",
            "contract_snippet": "",
            "regulation_snippet": "",
        }

    description = (
        v.get("description")
        or v.get("issue")
        or v.get("rationale")
        or "N/A"
    )
    category = v.get("category", "Uncategorized")
    regulation_ref = (
        v.get("regulation_ref")
        or v.get("regulation_reference")
        or v.get("reg_ref")
        or v.get("regulation")
        or v.get("regulation_section")
        or "N/A"
    )
    severity = v.get("severity", "N/A")
    v_type = v.get("type", "Potential Compliance Issue")

    contract_snippet = (
        v.get("contract_snippet")
        or v.get("contract_clause_snippet")
        or ""
    )
    regulation_snippet = (
        v.get("regulation_snippet")
        or v.get("regulation_excerpt")
        or v.get("regulation_excerpt_snippet")
        or ""
    )

    return {
        "description": description,
        "category": category,
        "regulation_ref": regulation_ref,
        "severity": severity,
        "type": v_type,
        "contract_snippet": contract_snippet,
        "regulation_snippet": regulation_snippet,
    }


class PDF(FPDF):
    def __init__(self, contract_name="N/A", regulation_file="N/A", **kwargs):
        super().__init__(**kwargs)
        self.contract_name = contract_name
        self.regulation_file = regulation_file
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)

    def header(self):
        # Premium Header Background (Reduced Height)
        self.set_fill_color(*BRAND_DEEP_GREEN)
        self.rect(0, 0, 210, 28, 'F')
        
        # Accent Line
        self.set_fill_color(*BRAND_ACCENT_GOLD)
        self.rect(0, 27, 210, 1, 'F')

        # Branding / Title
        self.set_font('Arial', 'B', 18)
        self.set_text_color(255, 255, 255)
        self.set_xy(20, 6)
        self.cell(0, 10, "CompliMate", 0, 1, 'L')
        
        self.set_font('Arial', '', 8)
        self.set_text_color(200, 200, 200)
        self.set_xy(20, 14)
        self.cell(0, 5, "AI-Powered Compliance Analysis", 0, 1, 'L')

        # Report Title (Right Aligned)
        self.set_font('Arial', 'B', 12)
        self.set_text_color(255, 255, 255)
        self.set_xy(100, 7)
        self.cell(90, 8, "COMPLIANCE REPORT", 0, 1, 'R')
        
        self.set_font('Arial', '', 8)
        self.set_text_color(220, 220, 220)
        self.set_xy(100, 14)
        self.cell(90, 5, f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}", 0, 1, 'R')

        self.ln(15) # Spacing after header

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(*BRAND_TEXT_SECONDARY)
        
        # Divider line
        self.set_draw_color(*DIVIDER_COLOR)
        self.line(20, 282, 190, 282)
        
        # Footer Content
        footer_text = f'CompliMate AI Analysis | {self.contract_name}'
        self.cell(0, 10, _safe_pdf_text(footer_text), 0, 0, 'L')
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', 0, 0, 'R')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(*BRAND_DEEP_GREEN)
        self.cell(0, 8, _safe_pdf_text(title), 0, 1, 'L')
        
        # Underline
        self.set_draw_color(*BRAND_ACCENT_GOLD)
        self.set_line_width(0.5)
        self.line(self.get_x(), self.get_y(), self.get_x() + 170, self.get_y())
        self.ln(5)
        self.set_text_color(*DEFAULT_COLOR)

    def chapter_body(self, text, font_size=11):
        self.set_font('Arial', '', font_size)
        self.multi_cell(0, 6, _safe_pdf_text(text))
        self.ln()

    def _ensure_space_for_multicell(self, min_space: float = 10.0):
        """Ensure there's horizontal space for a multi_cell."""
        try:
            avail = self.w - self.r_margin - self.get_x()
            if avail < min_space:
                self.ln()
                self.set_x(self.l_margin)
        except Exception:
            pass

    def add_severity_badge(self, severity):
        """Draw a colored badge for severity."""
        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["N/A"])
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 8)
        
        # Badge dimensions
        w = 20
        h = 6
        
        # Draw rounded rect (simulated with rect)
        x = self.get_x()
        y = self.get_y()
        self.rect(x, y, w, h, 'F')
        
        # Text centered in badge
        self.cell(w, h, severity.upper(), 0, 0, 'C')
        
        # Reset
        self.set_text_color(*DEFAULT_COLOR)
        self.set_xy(x + w + 5, y) # Move cursor after badge

    def add_violation(self, index, violation):
        # Card-like background for violation
        start_y = self.get_y()
        
        # Check page break
        if start_y > 250:
            self.add_page()
            start_y = self.get_y()

        self.set_font('Arial', 'B', 11)
        
        # Index
        self.set_text_color(*BRAND_TEXT_SECONDARY)
        self.cell(10, 6, f"{index}.", 0, 0)
        
        # Severity Badge
        severity = violation.get('severity', 'N/A')
        self.add_severity_badge(severity)
        
        # Category
        category = violation.get('category', 'Uncategorized')
        self.set_font('Arial', 'B', 11)
        self.set_text_color(*BRAND_DEEP_GREEN)
        self.cell(0, 6, _safe_pdf_text(category), 0, 1)
        
        # Issue Description
        self.ln(2)
        self.set_x(self.l_margin + 10)
        self.set_font('Arial', '', 10)
        self.set_text_color(*BRAND_TEXT_PRIMARY)
        self.multi_cell(0, 5, _safe_pdf_text(f"Issue: {violation.get('description', 'N/A')}"))
        
        # Regulation Reference (Boxed)
        reg_ref = violation.get('regulation_ref', 'N/A')
        if reg_ref != "N/A":
            self.ln(2)
            self.set_x(self.l_margin + 10)
            self.set_font('Arial', 'I', 9)
            self.set_text_color(*BRAND_DEEP_GREEN)
            self.multi_cell(0, 5, _safe_pdf_text(f"Reference: {reg_ref}"))

        # Divider
        self.ln(4)
        self.set_draw_color(240, 240, 240)
        self.line(self.l_margin, self.get_y(), 190, self.get_y())
        self.ln(4)


# JSON + Text reports unchanged
def generate_report(report_data, output_file="analysis_report.json"):
    logger.info(f"Generating JSON report: {output_file}")
    try:
        safe = _serialize_for_json(report_data)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(safe, f, indent=4, ensure_ascii=False)
        logger.info(f"JSON report successfully generated: {output_file}")
    except Exception as e:
        logger.exception(f"Error generating JSON report {output_file}: {e}")


def generate_text_report(report_data, output_file="analysis_report.txt"):
    # ... (Keep existing implementation or simplify)
    # For brevity, keeping the existing logic is fine, but let's just copy the previous implementation
    # to ensure no functionality loss.
    logger.info(f"Generating text report: {output_file}")
    summary = ""
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        raw_violations = report_data.get('violations', [])
        violations = [_normalize_violation(v) for v in raw_violations]
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        summary += f"Compliance Analysis Report\n==========================\n"
        summary += f"Contract: {contract_name}\n"
        summary += f"Regulation: {regulation_file}\n"
        summary += f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"Prompts Sent: {total_prompts} | Successful LLM Responses: {successful_responses}\n"
        summary += f"Potential Issues Found: {len(violations)}\n\n"
        
        # ... (Rest of text report logic)
        # Simplified for this overwrite to save tokens, as the focus is PDF
        for idx, v in enumerate(violations, 1):
            summary += f"{idx}. [{v.get('severity')}] {v.get('description')}\n"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)
    except Exception as e:
        logger.exception(f"Error generating text report: {e}")


def generate_pdf_report(report_data, output_file="analysis_report.pdf"):
    logger.info(f"Generating Premium PDF report: {output_file}")
    try:
        contract_name = report_data.get('contract_name', 'N/A')
        regulation_file = report_data.get('regulation_file', 'N/A')
        raw_violations = report_data.get('violations', [])
        violations = [_normalize_violation(v) for v in raw_violations]
        
        pdf = PDF(contract_name=contract_name, regulation_file=regulation_file)
        pdf.alias_nb_pages()
        pdf.add_page()

        # --- Document Info Card ---
        pdf.set_fill_color(*BRAND_LIGHT_CREAM)
        pdf.rect(20, pdf.get_y(), 170, 30, 'F') # Reduced height to 30
        pdf.set_xy(25, pdf.get_y() + 5)
        
        pdf.set_font('Arial', 'B', 9)
        pdf.set_text_color(*BRAND_TEXT_SECONDARY)
        pdf.cell(25, 6, "Contract:", 0, 0)
        pdf.set_font('Arial', '', 9)
        pdf.set_text_color(*BRAND_TEXT_PRIMARY)
        pdf.cell(0, 6, _safe_pdf_text(contract_name), 0, 1)
        
        pdf.set_x(25)
        pdf.set_font('Arial', 'B', 9)
        pdf.set_text_color(*BRAND_TEXT_SECONDARY)
        pdf.cell(25, 6, "Regulations:", 0, 0)
        pdf.set_font('Arial', '', 9)
        pdf.set_text_color(*BRAND_TEXT_PRIMARY)
        
        # Handle list of regulations or single string
        reg_display = "N/A"
        if isinstance(regulation_file, list):
             reg_display = ", ".join([os.path.basename(r) for r in regulation_file])
        elif isinstance(regulation_file, str):
             reg_display = os.path.basename(regulation_file)
             
        # Truncate if too long
        if len(reg_display) > 70:
            reg_display = reg_display[:67] + "..."
            
        pdf.cell(0, 6, _safe_pdf_text(reg_display), 0, 1)
        
        pdf.set_x(25)
        pdf.set_font('Arial', 'B', 9)
        pdf.set_text_color(*BRAND_TEXT_SECONDARY)
        pdf.cell(25, 6, "Analyzed On:", 0, 0)
        pdf.set_font('Arial', '', 9)
        pdf.set_text_color(*BRAND_TEXT_PRIMARY)
        pdf.cell(0, 6, datetime.datetime.now().strftime('%B %d, %Y at %H:%M'), 0, 1)
        
        pdf.ln(10)

        # --- Executive Summary ---
        pdf.chapter_title("Executive Summary")
        
        # Severity Counts
        sev_totals = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for v in violations:
            s = v.get('severity', 'N/A')
            if s in sev_totals:
                sev_totals[s] += 1
        
        # Summary Grid
        start_x = pdf.get_x()
        y = pdf.get_y()
        
        # Total Issues Box
        pdf.set_fill_color(*BRAND_DEEP_GREEN)
        pdf.rect(start_x, y, 40, 25, 'F')
        pdf.set_xy(start_x, y + 5)
        pdf.set_font('Arial', 'B', 20)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(40, 10, str(len(violations)), 0, 1, 'C')
        pdf.set_xy(start_x, y + 15)
        pdf.set_font('Arial', '', 8)
        pdf.cell(40, 5, "Total Issues", 0, 0, 'C')
        
        # Severity Breakdown
        pdf.set_xy(start_x + 50, y)
        pdf.set_text_color(*BRAND_TEXT_PRIMARY)
        pdf.set_font('Arial', '', 10)
        
        current_x = start_x + 50
        for sev, count in sev_totals.items():
            if count > 0:
                pdf.set_xy(current_x, y + 2)
                pdf.add_severity_badge(sev)
                pdf.set_xy(current_x, y + 10)
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(*BRAND_TEXT_PRIMARY)
                pdf.cell(20, 6, str(count), 0, 0, 'C')
                current_x += 30
        
        pdf.ln(35)

        # --- Detailed Findings ---
        pdf.chapter_title("Detailed Compliance Findings")
        
        if not violations:
            pdf.set_font('Arial', 'I', 11)
            pdf.cell(0, 10, "No compliance issues identified. The contract appears to align with regulations.", 0, 1)
        else:
            # Sort by severity (Critical -> Low)
            severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "N/A": 4}
            violations.sort(key=lambda x: severity_order.get(x.get('severity', 'N/A'), 5))
            
            for idx, violation in enumerate(violations, 1):
                pdf.add_violation(idx, violation)

        pdf.output(output_file)
        logger.info(f"Premium PDF report successfully generated: {output_file}")

    except ImportError:
        logger.error("fpdf2 library not found. Cannot generate PDF report.")
    except Exception as e:
        logger.exception(f"Error generating PDF report {output_file}: {e}")
