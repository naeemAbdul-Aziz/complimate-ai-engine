# report_generator.py
import json
import logging
import datetime
import os
from fpdf import FPDF
from typing import Any


# Helpers
def _serialize_for_json(obj: Any, _seen: set | None = None) -> Any:
    """Recursively convert an object graph into JSON-serializable primitives.

    Replaces circular references with the string '<circular ref>' and
    converts unknown objects to their string representation.
    """
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
        # keep it in seen to avoid re-traversal; it's OK for fallback
        pass


def _safe_pdf_text(text: Any) -> str:
    """Normalize text for fpdf (latin-1 core fonts).

    Replaces common Unicode punctuation with ASCII equivalents and
    falls back to lossy latin-1 replacement for any remaining characters.
    """
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
    """Normalize violation dictionaries to a common schema used by reporters.

    Handles variations from different pipeline stages (primary extraction vs.
    refinement), such as using 'issue' instead of 'description', or missing
    'type' fields.
    """
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
        self.cell(0, 5, _safe_pdf_text(f'Compliance Report: {self.contract_name}'), 0, 1, 'C')
        self.set_text_color(*DEFAULT_COLOR)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        footer_text = (
            f'Regulation: {os.path.basename(self.regulation_file)} | Page {self.page_no()}/{{nb}}'
        )
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, _safe_pdf_text(footer_text), 0, 0, 'C')
        self.set_text_color(*DEFAULT_COLOR)

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 13)
        self.set_text_color(*BRAND_GREEN)
        self.cell(0, 10, _safe_pdf_text(title), 0, 1, 'L')
        self.set_text_color(*DEFAULT_COLOR)
        self.ln(2)

    def chapter_body(self, text, font_size=11):
        self.set_font('Arial', '', font_size)
        self.multi_cell(0, 6, _safe_pdf_text(text))
        self.ln()

    def _ensure_space_for_multicell(self, min_space: float = 10.0):
        """Ensure there's horizontal space for a multi_cell; if not, advance to next line.

        Uses page width and right margin to compute available width. If available
        width is less than `min_space`, move to the next line and reset X to left
        margin so subsequent `multi_cell(0, ...)` calls have room.
        """
        try:
            avail = self.w - self.r_margin - self.get_x()
            if avail < min_space:
                # Move to next line and reset to left margin
                self.ln()
                try:
                    self.set_x(self.l_margin)
                except Exception:
                    # Fall back to x= left margin if attribute missing
                    self.set_x(10)
        except Exception:
            # Defensive: if anything goes wrong, just move to next line
            try:
                self.ln()
                self.set_x(self.l_margin)
            except Exception:
                pass

    def add_violation(self, index, violation):
        self.set_font('Arial', 'B', 11)
        severity = violation.get('severity', 'N/A')
        category = violation.get('category', 'Uncategorized')
        type = violation.get('type', 'Potential Compliance Issue')  # Get the type
        color = SEVERITY_COLORS.get(severity, DEFAULT_COLOR)

        self.set_text_color(*color)
        if type == "Universal Clause Issue":
            self.cell(0, 6, _safe_pdf_text(f"{index}. [Universal Clause] {violation.get('description', 'N/A')}"), 0, 1)  # Different format
        else:
            self.cell(0, 6, _safe_pdf_text(f"{index}. [{severity}] {category}"), 0, 1)  # Original format
        self.set_text_color(*DEFAULT_COLOR)

        self.set_font('Arial', '', 10)
        # Ensure there's space for the multi-cell; if not, move to next line
        self._ensure_space_for_multicell()
        # Use a small manual indent rather than relying on current X position
        try:
            self.set_x(self.l_margin + 4)
        except Exception:
            pass
        self.multi_cell(0, 5, _safe_pdf_text(f"Issue: {violation.get('description', 'N/A')}"))
        if type != "Universal Clause Issue":
            self._ensure_space_for_multicell()
            try:
                self.set_x(self.l_margin + 4)
            except Exception:
                pass
            self.multi_cell(0, 5, _safe_pdf_text(f"Regulation Ref: {violation.get('regulation_ref', 'N/A')}"))  # Only for regulation issues
        self.ln(3)



# JSON + Text reports unchanged (kept for completeness)
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

        # Executive Summary & MRIA (Phase 1)
        try:
            from config.settings import settings as app_settings
        except Exception:
            app_settings = type("obj", (), {"REPORT_ENHANCED_MODE": True, "INCLUDE_EXEC_SUMMARY": True, "INCLUDE_MRIA": True})()

        if getattr(app_settings, 'REPORT_ENHANCED_MODE', True):
            # Totals by severity/category
            sev_totals = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "N/A": 0}
            cat_totals = {}
            for v in violations:
                sev = v.get('severity', 'N/A')
                sev_totals[sev] = sev_totals.get(sev, 0) + 1
                cat = v.get('category', 'Uncategorized')
                cat_totals[cat] = cat_totals.get(cat, 0) + 1

            if getattr(app_settings, 'INCLUDE_EXEC_SUMMARY', True):
                summary += "Executive Summary\n------------------\n"
                total = len(violations)
                summary += f"Total Findings: {total}\n"
                summary += "By Severity:\n" + "\n".join([f"  {k}: {v}" for k, v in sev_totals.items() if v > 0]) + "\n"
                summary += "By Category:\n" + "\n".join([f"  {k}: {v}" for k, v in cat_totals.items()]) + "\n\n"

            if getattr(app_settings, 'INCLUDE_MRIA', True):
                mria = [v for v in violations if v.get('severity') in ("Critical", "High")]
                summary += "Matters Requiring Immediate Attention (MRIA)\n-------------------------------------------\n"
                if mria:
                    for idx, v in enumerate(mria, start=1):
                        summary += f"{idx}. {v.get('description','N/A')}\n   Regulation Ref: {v.get('regulation_ref','N/A')}\n"
                else:
                    summary += "None.\n"
                summary += "\n"

        regulation_violations = [v for v in violations if (v.get('type') or 'Potential Compliance Issue') == 'Potential Compliance Issue']
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

        # Grouped rendering if present
        grouped = report_data.get('grouped') or {}
        if grouped and isinstance(grouped, dict) and grouped.get('categories'):
            summary += "\nGrouped Regulatory Compliance Issues:\n--------------------------------------\n"
            for cat in grouped.get('categories', []):
                summary += f"Category: {cat.get('name', 'Uncategorized')}\n"
                for reg in cat.get('regulations', []):
                    for idx, item in enumerate(reg.get('items', []), start=1):
                        nv = _normalize_violation(item)
                        summary += f"    {idx}. [{nv.get('severity','N/A')}] {nv.get('description','N/A')}\n"
                        summary += f"       Regulation Ref: {nv.get('regulation_ref','N/A')}\n"
                        inst = item.get('instances') or []
                        if inst:
                            summary += f"       Instances: {len(inst)}\n"
        else:
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
        raw_violations = report_data.get('violations', [])
        violations = [_normalize_violation(v) for v in raw_violations]
        total_prompts = report_data.get('total_prompts_sent', 'N/A')
        successful_responses = report_data.get('successful_responses', 'N/A')

        pdf = PDF(contract_name=contract_name, regulation_file=regulation_file)
        pdf.alias_nb_pages()
        pdf.add_page()

        # Optional Unicode font support (configured via settings)
        unicode_font_loaded = False
        try:
            from config.settings import settings as app_settings  # local import to avoid circulars
            if getattr(app_settings, 'USE_UNICODE_FONT', False):
                font_path = getattr(app_settings, 'UNICODE_FONT_PATH', 'fonts/DejaVuSans.ttf')
                if os.path.exists(font_path):
                    try:
                        # Register the same TTF for common style variants so calls like set_font('Unicode','B',..) succeed.
                        pdf.add_font('Unicode', '', font_path, uni=True)
                        # Register 'B', 'I', and 'BI' variants using same file as a fallback so style lookups succeed.
                        try:
                            pdf.add_font('Unicode', 'B', font_path, uni=True)
                        except Exception:
                            pass
                        try:
                            pdf.add_font('Unicode', 'I', font_path, uni=True)
                        except Exception:
                            pass
                        try:
                            pdf.add_font('Unicode', 'BI', font_path, uni=True)
                        except Exception:
                            pass
                        unicode_font_loaded = True
                        logger.info(f"Loaded unicode font for PDF reporting: {font_path}")
                    except Exception as fe:
                        logger.warning(f"Failed registering unicode font '{font_path}': {fe}; falling back to core fonts.")
                else:
                    logger.info(f"Unicode font path not found: {font_path}. Using core fonts. (Set USE_UNICODE_FONT=False or supply the TTF file.)")
        except Exception:
            logger.debug("Unicode font load attempt skipped due to settings import issue.")

        base_font = 'Unicode' if unicode_font_loaded else 'Arial'
        pdf.set_font(base_font, 'B', 18)
        pdf.set_text_color(*BRAND_GREEN)
        pdf.cell(0, 20, _safe_pdf_text("Contract Compliance Analysis Report"), 0, 1, 'C')
        pdf.set_text_color(*DEFAULT_COLOR)
        pdf.ln(4)
        pdf.set_font(base_font, '', 12)
        pdf.cell(0, 10, _safe_pdf_text(f"Contract: {contract_name}"), 0, 1, 'C')
        pdf.cell(0, 10, _safe_pdf_text(f"Regulation Analyzed: {os.path.basename(regulation_file)}"), 0, 1, 'C')
        pdf.cell(0, 10, _safe_pdf_text(f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"), 0, 1, 'C')
        pdf.ln(10)

        pdf.chapter_title(_safe_pdf_text("CompliMate Analysis Summary"))
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 5, _safe_pdf_text(f"Total potential compliance issues identified: {len(violations)}"))

        # Executive Summary & MRIA (Phase 1)
        try:
            from config.settings import settings as app_settings
        except Exception:
            app_settings = type("obj", (), {"REPORT_ENHANCED_MODE": True, "INCLUDE_EXEC_SUMMARY": True, "INCLUDE_MRIA": True})()

        if getattr(app_settings, 'REPORT_ENHANCED_MODE', True):
            # Severity totals
            sev_totals = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "N/A": 0}
            for v in violations:
                sev = v.get('severity', 'N/A')
                sev_totals[sev] = sev_totals.get(sev, 0) + 1

            if getattr(app_settings, 'INCLUDE_EXEC_SUMMARY', True):
                pdf.ln(2)
                pdf.set_font('Arial', 'B', 11)
                pdf.cell(0, 6, _safe_pdf_text("Executive Summary"), 0, 1)
                pdf.set_font('Arial', '', 11)
                for k, v in sev_totals.items():
                    if v > 0:
                        pdf.cell(20)
                        pdf.cell(0, 5, _safe_pdf_text(f"- {k}: {v}"), 0, 1)

            if getattr(app_settings, 'INCLUDE_MRIA', True):
                mria = [v for v in violations if v.get('severity') in ("Critical", "High")]
                pdf.ln(2)
                pdf.set_font('Arial', 'B', 11)
                pdf.cell(0, 6, "Matters Requiring Immediate Attention (MRIA)", 0, 1)
                pdf.set_font('Arial', '', 11)
                if mria:
                        for idx, v in enumerate(mria, start=1):
                            pdf.cell(0, 5, _safe_pdf_text(f"{idx}. {v.get('description','N/A')}"), 0, 1)
                            pdf.cell(0, 5, _safe_pdf_text(f"   Regulation Ref: {v.get('regulation_ref','N/A')}") , 0, 1)
                else:
                    pdf.cell(0, 5, "None.", 0, 1)

        regulation_violations = [v for v in violations if (v.get('type') or 'Potential Compliance Issue') == 'Potential Compliance Issue']
        universal_clause_issues = [v for v in violations if v.get('type') == 'Universal Clause Issue']

        pdf.ln(2)
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, _safe_pdf_text("Regulatory Compliance Issues by Severity:"), 0, 1)
        pdf.set_font('Arial', '', 11)
        severity_counts = {"High": 0, "Medium": 0, "Low": 0, "N/A": 0, "Uncategorized": 0}
        for v in regulation_violations:  # Only count severity for regulation violations
            sev = v.get('severity', 'N/A')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        for severity, count in severity_counts.items():
            if count > 0:
                pdf.set_text_color(*SEVERITY_COLORS.get(severity, DEFAULT_COLOR))
                pdf.cell(20)
                pdf.cell(0, 5, _safe_pdf_text(f"- {severity}: {count}"), 0, 1)
        pdf.set_text_color(*DEFAULT_COLOR)
        pdf.ln(5)

        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 6, _safe_pdf_text("Universal Clause Issues:"), 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.cell(20)
        pdf.cell(0, 5, _safe_pdf_text(f"- Total: {len(universal_clause_issues)}"), 0, 1)

        pdf.add_page()
        grouped = report_data.get('grouped') or {}
        if grouped and isinstance(grouped, dict) and grouped.get('categories'):
            pdf.chapter_title("Grouped Regulatory Compliance Issues")
            for cat in grouped.get('categories', []):
                pdf.set_font('Arial', 'B', 12)
                pdf.set_text_color(*BRAND_GREEN)
                pdf.cell(0, 8, _safe_pdf_text(f"Category: {cat.get('name','Uncategorized')}"), 0, 1)
                pdf.set_text_color(*DEFAULT_COLOR)
                for reg in cat.get('regulations', []):
                    for idx, item in enumerate(reg.get('items', []), start=1):
                        nv = _normalize_violation(item)
                        pdf.add_violation(idx, nv)
                        # Add single per-item regulation reference directly under issue
                        pdf.set_font('Arial', '', 10)
                        pdf.multi_cell(0, 5, _safe_pdf_text(f"      Regulation Ref: {nv.get('regulation_ref','N/A')}"))
        else:
            pdf.chapter_title("Detailed Regulatory Compliance Issues")
            if regulation_violations:
                for idx, violation in enumerate(regulation_violations, start=1):
                    pdf.add_violation(idx, violation)
            else:
                pdf.set_font('Arial', '', 11)
                pdf.multi_cell(0, 5, _safe_pdf_text("No potential regulatory compliance issues identified during the analysis."))

        pdf.add_page()
        pdf.chapter_title("Universal Clause Issues")
        if universal_clause_issues:
            for idx, violation in enumerate(universal_clause_issues, start=1):
                pdf.add_violation(idx, violation)
        else:
            pdf.set_font('Arial', '', 11)
            pdf.multi_cell(0, 5, _safe_pdf_text("No universal clause issues identified during the analysis."))

        # fpdf2 output signature expects either a single path or keyword args; remove legacy second positional arg
        pdf.output(output_file)
        logger.info(f"PDF report successfully generated: {output_file}")
    except ImportError:
        logger.error("fpdf2 library not found. Cannot generate PDF report. Install with 'pip install fpdf2'")
    except Exception as e:
        logger.exception(f"Error generating PDF report {output_file}: {e}")
