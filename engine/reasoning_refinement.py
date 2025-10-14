"""Secondary reasoning refinement module.

This module provides a function to refine initially detected violations using a
higher reasoning-capacity OpenAI model. The goal is to:
 1. Remove false positives (hallucinations / misalignments)
 2. Merge duplicates describing the same regulatory issue
 3. Add severity and confidence scoring
 4. Optionally enrich each violation with a concise justification rationale

The function is intentionally lightweight and pure (no I/O besides model calls)
so it can be swapped or extended. It expects violations as list[dict] with at
least keys: 'violation_id', 'issue', 'contract_snippet', 'regulation_excerpt'.

If the secondary model errors, it falls back to returning the original list.
"""
from __future__ import annotations

from typing import List, Dict, Any, Generator
import json
import logging
import time
import random

from config.settings import settings as app_settings

# Prefer the official OpenAI client for strict control of timeouts/retries
try:  # pragma: no cover
    from openai import OpenAI as OpenAIClient  # type: ignore
    from openai import APITimeoutError as OpenAIAPITimeoutError  # type: ignore
except Exception:  # pragma: no cover
    OpenAIClient = None  # type: ignore
    OpenAIAPITimeoutError = Exception  # type: ignore

logger = logging.getLogger(__name__)

# --- NEW CHUNKING UTILITY ---
def _chunk_list(data: List[Any], chunk_size: int) -> Generator[List[Any], None, None]:
    """Yield successive n-sized chunks from a list."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]
# ----------------------------

REFINEMENT_SYSTEM_PROMPT = (
    "You are a meticulous compliance analyst. You receive a JSON array of candidate "
    "violations extracted from a contract against regulations. Your tasks: "
    "1) Remove entries that lack clear regulatory basis. 2) Merge duplicates. "
    "3) For each remaining violation add: severity (Low|Medium|High|Critical), "
    "confidence (0-1 float), rationale (one concise sentence). Output ONLY valid JSON array."
)

REFINEMENT_SCHEMA_HINT = {
    "violation_id": "string - keep original id if possible, or generate stable merged id",
    "issue": "string",
    "contract_snippet": "string",
    "regulation_excerpt": "string",
    "severity": "Low|Medium|High|Critical",
    "confidence": "float 0-1",
    "rationale": "one sentence justification",
}

def _build_refinement_prompt(violations: List[Dict[str, Any]]) -> str:
    sample_schema = json.dumps(REFINEMENT_SCHEMA_HINT, indent=2)
    payload = json.dumps(violations, ensure_ascii=False, indent=2)
    return (
        f"SYSTEM INSTRUCTIONS:\n{REFINEMENT_SYSTEM_PROMPT}\n\n"
        f"Schema hint for each object: {sample_schema}\n\n"
        f"Candidate violations JSON array (Length: {len(violations)}) follows:\n{payload}\n\n"
        "Return the refined JSON array only."
    )


def refine_violations(violations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Refine violations via secondary reasoning model, processing in chunks.

    Returns refined list. On error returns original list (logged).
    """
    if not violations:
        return violations

    if not app_settings.ENABLE_SECONDARY_REASONING:
        return violations

    if OpenAIClient is None:
        logger.warning("OpenAI client unavailable; skipping secondary refinement.")
        return violations

    
    # Use chunking to reduce prompt size and prevent timeouts. Max 15 items per chunk.
    CHUNK_SIZE = 15 
    chunks = list(_chunk_list(violations, CHUNK_SIZE))
    
    all_refined_violations: List[Dict[str, Any]] = []
    
    # Configure constants from settings
    max_retries = max(0, int(getattr(app_settings, "SECONDARY_REASONING_MAX_RETRIES", 1)))
    # Note: Using new default from settings (60.0s)
    request_timeout = float(getattr(app_settings, "SECONDARY_REASONING_REQUEST_TIMEOUT", 60.0))
    # Note: Using new default from settings (90.0s)
    deadline = float(getattr(app_settings, "SECONDARY_REASONING_DEADLINE_SECONDS", 90.0))

    try:
        client = OpenAIClient(api_key=app_settings.OPENAI_API_KEY)  # type: ignore[arg-type]
        call_client = client.with_options(timeout=request_timeout, max_retries=0)
        
        # Process chunks sequentially
        for i, chunk in enumerate(chunks):
            chunk_start_time = time.monotonic()
            
            prompt = _build_refinement_prompt(chunk)
            
            attempt = 0
            last_err: Exception | None = None
            raw: str | None = None
            
            messages = [
                {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            
            logger.info("Starting refinement for Chunk %d/%d (Size: %d)...", i + 1, len(chunks), len(chunk))
            
            while attempt <= max_retries:
                try:
                    resp = call_client.chat.completions.create(  # type: ignore[attr-defined]
                        model=app_settings.SECONDARY_REASONING_MODEL,
                        messages=messages,  # type: ignore[arg-type]
                        temperature=0,
                    )
                    raw = resp.choices[0].message.content if resp.choices else "[]"
                    logger.info("Chunk %d/%d successful in %.2fs.", i + 1, len(chunks), time.monotonic() - chunk_start_time)
                    break # Success, break out of retry loop
                except OpenAIAPITimeoutError as e:
                    last_err = e
                    # Adjusted backoff
                    delay = min(1.0 * (2 ** attempt), 4.0) + random.uniform(0.0, 0.5) 
                    elapsed = time.monotonic() - chunk_start_time
                    logger.warning(
                        "Chunk %d/%d, attempt %d/%d failed (Request timed out.). Retrying in %.2fs...",
                        i + 1, len(chunks), attempt + 1, max_retries + 1, delay,
                    )
                    if elapsed + delay > deadline:
                        logger.error("Refinement deadline reached (%.2fs) during chunk processing. Aborting.", deadline)
                        raise last_err # Re-raise error to trigger main failure path
                    time.sleep(delay)
                    attempt += 1
                except Exception as e:
                    last_err = e
                    delay = 0.5 + random.uniform(0.0, 0.5)
                    elapsed = time.monotonic() - chunk_start_time
                    logger.warning(
                        "Chunk %d/%d, attempt %d/%d failed (%s). Retrying in %.2fs...",
                        i + 1, len(chunks), attempt + 1, max_retries + 1, str(e), delay,
                    )
                    if elapsed + delay > deadline:
                        logger.error("Refinement deadline reached (%.2fs) during chunk processing. Aborting.", deadline)
                        raise last_err # Re-raise error to trigger main failure path
                    time.sleep(delay)
                    attempt += 1
            
            # Post-chunk processing
            if raw is None:
                # If all retries failed for this chunk
                logger.error("Chunk %d/%d failed after all retries. Aborting refinement.", i + 1, len(chunks))
                raise last_err or RuntimeError("Chunk refinement failure")

            # Attempt to parse JSON and clean
            refined = json.loads(raw)
            if isinstance(refined, list):
                # Apply sanity filtering and deduplication within the chunk
                cleaned: List[Dict[str, Any]] = []
                seen_keys = set()
                for v in refined:
                    if not isinstance(v, dict):
                        continue
                    # Ensure the new mandatory fields are present
                    if not (v.get("severity") and v.get("confidence") is not None and v.get("rationale")):
                        # Logging warning but proceeding to store the partially completed item
                        logger.warning("Refined violation in chunk %d missing required field (severity, confidence, or rationale).", i+1)
                        
                    vid = str(v.get("violation_id") or len(cleaned) + 1)
                    # Deduplication logic (issue and snippet)
                    dedupe_key = (v.get("issue"), v.get("contract_snippet"))
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    cleaned.append(v)
                
                all_refined_violations.extend(cleaned)
            else:
                logger.warning("Chunk %d/%d model returned non-list JSON; discarding chunk results.", i + 1, len(chunks))
                # Do not re-raise, but skip results for this chunk

        # Final cross-chunk deduplication 
        final_cleaned: List[Dict[str, Any]] = []
        final_seen_keys = set()
        for v in all_refined_violations:
             dedupe_key = (v.get("issue"), v.get("contract_snippet"))
             if dedupe_key not in final_seen_keys:
                 final_cleaned.append(v)
                 final_seen_keys.add(dedupe_key)

        logger.info(
            "Secondary refinement processed %d violations in %d chunks, resulting in %d final unique violations.", 
            len(violations), 
            len(chunks), 
            len(final_cleaned)
        )
        return final_cleaned

    except Exception as e:  # pragma: no cover - fall back path
        logger.exception("Secondary reasoning refinement failed during chunk processing; returning original violations: %s", e)
        # If any chunk fails critically, return the original list
        return violations