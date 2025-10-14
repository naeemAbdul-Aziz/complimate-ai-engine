# Troubleshooting Guide

This guide covers common operational issues encountered while running the CompliMate AI Engine and how to resolve them.

## PDF Library Conflicts

### Symptom
Warnings like:
```
You have both PyFPDF & fpdf2 installed.
```
Or startup log warning:
```
PDF library conflict: both 'pypdf' and 'PyPDF2' installed.
```

### Cause
Multiple PDF parsing/rendering libraries that share overlapping modules or legacy namespaces are installed simultaneously. This can lead to unpredictable imports or duplicated functionality.

### Recommended Standard
Use one of:
- `pypdf` (actively maintained fork of PyPDF2)  ✅ Recommended
- `PyPDF2` (older; maintenance reduced)
- `fpdf2` (modern fork for PDF generation — not parsing)

Avoid installing BOTH `pypdf` and `PyPDF2` together. Avoid legacy `fpdf` (PyFPDF) unless explicitly needed.

### Resolution (Windows PowerShell)
```powershell
pip uninstall PyPDF2 -y
pip uninstall pypdf -y   # (Only if you want a clean slate)
pip uninstall fpdf -y    # Remove legacy PyFPDF if present
pip install pypdf        # Reinstall the preferred parser
# (Optional for PDF generation)
pip install fpdf2
```

### Verification
```powershell
python - <<'PY'
import importlib
print("pypdf:", bool(importlib.util.find_spec('pypdf')))
print("PyPDF2:", bool(importlib.util.find_spec('PyPDF2')))
print("fpdf (legacy):", bool(importlib.util.find_spec('fpdf')))
PY
```
Ensure only the intended libraries print `True`.

---

## OpenAI 429 / Rate Limit Cooldown

### Symptom
Repeated log lines:
```
HTTP/1.1 429 Too Many Requests
Rate limit related failure while processing ... (consecutive=1)
```
Health endpoint shows:
```json
{
  "cooldown_active": true,
  "cooldown_remaining_seconds": 42
}
```

### Cause
Embedding or model requests exceed quota or rate thresholds.

### Behavior
The regulation index rebuild enters an exponential cooldown after each consecutive rate-limit sequence to avoid thrashing the API.

### Resolution
1. Verify billing/quota in OpenAI dashboard.
2. Reduce immediate rebuild attempts (do not call rebuild in a loop).
3. If testing offline, unset `OPENAI_API_KEY` to skip auto-rebuild on startup.

---

## ChromaDB Collection Metadata Errors (`_type` key)

### Symptom
Earlier versions produced errors referencing missing `_type` in collection configuration.

### Current Status
Initialization now auto-recreates a corrupted collection or falls back to in-memory without failing `/health`.

### Manual Recovery (if needed)
```powershell
# Force clear vector store & metadata (run inside Python REPL)
from engine.regulation_manager import RegulationManager
rm = RegulationManager()
rm.force_clear_vector_store()
```

---

## No Regulations Indexed

### Symptom
`/health` returns:
```json
{"regulations_indexed": 0, "regulation_loaded": false}
```

### Cause
Rate limit blocked initial indexing OR no PDF regulation files present in `data/regulations`.

### Resolution
1. Confirm at least one `*.pdf` file exists in `data/regulations`.
2. Trigger rebuild via (future endpoint) or instantiate `RegulationManager().rebuild_index(force=True)` in a shell.
3. Resolve upstream 429 issues first.

---

## Logging Location
Logs default to `./logs` relative to repository root. Rotate/size configuration can be added later; current structure uses component-based loggers for `api`, `engine`, `parsing`, `retrieval`, `violation`, `reporting`, `storage`.

---

## Need More Help?
Open an issue with:
- Commit hash / version (`2.0.2`)
- `/health` JSON output
- Relevant log excerpt (first and last 30 lines around the failure)

This helps triage efficiently.
