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

from typing import List, Dict, Any, Generator, Tuple, DefaultDict
from collections import defaultdict, deque
import re
import json
import logging
import time
import random

from config.settings import settings as app_settings
from utils.cache import get_json, set_json, key_hash
from utils.circuit_breaker import SimpleCircuitBreaker

# Prefer the official OpenAI client for strict control of timeouts/retries
try:  # pragma: no cover
    from openai import OpenAI as OpenAIClient  # type: ignore
    from openai import APITimeoutError as OpenAIAPITimeoutError  # type: ignore
except Exception:  # pragma: no cover
    OpenAIClient = None  # type: ignore
    OpenAIAPITimeoutError = Exception  # type: ignore

logger = logging.getLogger(__name__)

# Circuit breaker (process-wide) for secondary refinement timeouts/failures
_secondary_breaker = SimpleCircuitBreaker(
    fail_threshold=int(getattr(app_settings, "SECONDARY_BREAKER_FAIL_THRESHOLD", 2)),
    reset_seconds=int(getattr(app_settings, "SECONDARY_BREAKER_RESET_SECONDS", 300)),
)

# Lightweight health tracker for adaptive failover
class _RefinementHealth:
    def __init__(self) -> None:
        self.window = int(getattr(app_settings, "REFINEMENT_WINDOW", 10))
        self.min_obs = int(getattr(app_settings, "REFINEMENT_MIN_OBSERVATIONS", 5))
        self.max_ratio = float(getattr(app_settings, "REFINEMENT_TIMEOUT_RATIO_MAX", 0.5))
        self._events: deque[str] = deque(maxlen=max(1, self.window))

    def record(self, outcome: str) -> None:
        # outcome in {"success", "timeout", "error"}
        if outcome not in ("success", "timeout", "error"):
            outcome = "error"
        self._events.append(outcome)

    def should_trip(self) -> bool:
        events = list(self._events)
        if len(events) < max(1, self.min_obs):
            return False
        bad = sum(1 for e in events if e in ("timeout", "error"))
        ratio = bad / max(1, len(events))
        return ratio >= self.max_ratio

_health = _RefinementHealth()

# --- NEW CHUNKING UTILITY ---
def _chunk_list(data: List[Any], chunk_size: int) -> Generator[List[Any], None, None]:
    """Yield successive n-sized chunks from a list."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]
# ----------------------------

def _extract_json_array(raw: str) -> List[Dict[str, Any]]:
    """Attempt to robustly extract a JSON array from model output.

    Returns an empty list on failure.
    """
    try:
        if not raw or not raw.strip():
            return []
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    # Try to find a bracketed array slice
    try:
        s = raw
        start = s.find("[")
        end = s.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end + 1]
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


def _norm_text(s: str) -> str:
    """Fast normalization for duplicate checks: lowercase, strip punctuation/extra space, trim."""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[\s\-–—]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _cluster_by_cat_reg(violations: List[Dict[str, Any]]) -> DefaultDict[Tuple[str, str], List[Dict[str, Any]]]:
    buckets: DefaultDict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for v in violations:
        cat = v.get("category") or "Uncategorized"
        reg = v.get("regulation_ref") or v.get("regulation_reference") or v.get("reg_ref") or v.get("regulation_excerpt") or "N/A"
        buckets[(cat, str(reg))].append(v)
    return buckets


def _is_duplicate(a: Dict[str, Any], b: Dict[str, Any], sim_threshold: float = 0.90) -> bool:
    """Decide if two violations are duplicates based on normalized description similarity and matching reg ref.

    Current implementation: exact normalized-match first; optional embedding similarity hook (disabled by default).
    """
    # Regulation reference must match to be considered duplicate
    a_reg = a.get("regulation_ref") or a.get("regulation_reference") or a.get("reg_ref") or "N/A"
    b_reg = b.get("regulation_ref") or b.get("regulation_reference") or b.get("reg_ref") or "N/A"
    if str(a_reg) != str(b_reg):
        return False

    a_desc = a.get("description") or a.get("issue") or ""
    b_desc = b.get("description") or b.get("issue") or ""
    a_n = _norm_text(a_desc)
    b_n = _norm_text(b_desc)
    if not a_n or not b_n:
        return False
    if a_n == b_n:
        return True

    # Optional: embedding similarity (placeholder hook)
    try:
        from config.settings import settings as app_settings  # local import
        if getattr(app_settings, "USE_EMBEDDING_SIMILARITY", False):
            # For now, use a simple Jaccard-like similarity on tokens as lightweight surrogate
            a_tokens = set(a_n.split())
            b_tokens = set(b_n.split())
            inter = len(a_tokens & b_tokens)
            union = max(1, len(a_tokens | b_tokens))
            sim = inter / union
            return sim >= getattr(app_settings, "DEDUPE_SIM_THRESHOLD", sim_threshold)
    except Exception:
        pass
    return False


def _merge_payload(into: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two duplicate violations: preserve category/reg_ref; combine instances; aggregate scores."""
    # Preserve metadata
    into.setdefault("category", other.get("category", "Uncategorized"))
    into.setdefault("regulation_ref", other.get("regulation_ref") or other.get("regulation_reference") or other.get("reg_ref") or "N/A")
    # Severity: take max by rank
    rank = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    sev_a = into.get("severity", "Low")
    sev_b = other.get("severity", "Low")
    into["severity"] = max([sev_a, sev_b], key=lambda s: rank.get(str(s), 0))
    # Confidence: average, keep min/max for transparency
    try:
        ca = float(into.get("confidence", 0))
        cb = float(other.get("confidence", 0))
        into["confidence_min"] = min(ca, cb) if "confidence_min" not in into else min(float(into["confidence_min"]), ca, cb)
        into["confidence_max"] = max(ca, cb) if "confidence_max" not in into else max(float(into["confidence_max"]), ca, cb)
        into["confidence"] = round((ca + cb) / 2, 3)
    except Exception:
        pass
    # Rationale: keep longer/clearer
    ra = (into.get("rationale") or "").strip()
    rb = (other.get("rationale") or "").strip()
    into["rationale"] = ra if len(ra) >= len(rb) else rb
    # Instances: collect evidence
    inst = into.setdefault("instances", [])
    inst.append({
        "contract_node_id": other.get("contract_node_id"),
        "regulation_node_id": other.get("regulation_node_id"),
        "contract_snippet": other.get("contract_snippet") or other.get("contract_clause_snippet"),
        "regulation_snippet": other.get("regulation_snippet") or other.get("regulation_excerpt") or other.get("regulation_excerpt_snippet"),
    })
    return into


def _consolidate_cluster(items: List[Dict[str, Any]], sim_threshold: float, max_prune_ratio: float, min_items: int) -> List[Dict[str, Any]]:
    """Within a category+reg cluster, dedupe only near-identical descriptions and consolidate instances.

    Guardrail: if prune ratio exceeds max_prune_ratio or results < min_items, return original items.
    """
    if len(items) <= 1:
        return items
    kept: List[Dict[str, Any]] = []
    for v in items:
        # ensure base structure carries over properly
        v = dict(v)
        v.setdefault("instances", [])
        v["instances"].append({
            "contract_node_id": v.get("contract_node_id"),
            "regulation_node_id": v.get("regulation_node_id"),
            "contract_snippet": v.get("contract_snippet") or v.get("contract_clause_snippet"),
            "regulation_snippet": v.get("regulation_snippet") or v.get("regulation_excerpt") or v.get("regulation_excerpt_snippet"),
        })
        merged = False
        for k in kept:
            if _is_duplicate(k, v, sim_threshold):
                _merge_payload(k, v)
                merged = True
                break
        if not merged:
            kept.append(v)

    pruned = len(items) - len(kept)
    if len(items) > 0:
        prune_ratio = pruned / len(items)
    else:
        prune_ratio = 0.0
    # Guardrail: prefer fail-open to avoid unintentionally hiding issues.
    if prune_ratio > max_prune_ratio or len(kept) < max(min_items, 1):
        # guardrail: return originals
        return items
    return kept

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
    "category": "string - preserve from source if present (e.g., Missing Obligation, Non-compliant Clause, Ambiguity)",
    "regulation_ref": "string - the specific regulation section/paragraph reference (e.g., 'Regulation 46(2)(a)')",
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

    # Respect both original and new alias toggle
    if not app_settings.ENABLE_SECONDARY_REASONING or not getattr(app_settings, 'SECONDARY_REFINEMENT_ENABLED', True):
        return violations

    if OpenAIClient is None:
        logger.warning("OpenAI client unavailable; skipping secondary refinement.")
        return violations

    if _secondary_breaker.is_open():
        logger.warning("Secondary refinement circuit open; skipping refinement and returning originals.")
        return violations
    
    # Use chunking to reduce prompt size and prevent timeouts. Max 15 items per chunk.
    CHUNK_SIZE = 12 
    chunks = list(_chunk_list(violations, CHUNK_SIZE))
    
    all_refined_violations: List[Dict[str, Any]] = []
    
    # Configure constants from settings
    max_retries = max(0, int(getattr(app_settings, "SECONDARY_REASONING_MAX_RETRIES", 1)))
    # Note: Using tuned defaults here to keep refinement bounded
    request_timeout = float(getattr(app_settings, "SECONDARY_REASONING_REQUEST_TIMEOUT", 60.0))
    deadline = float(getattr(app_settings, "SECONDARY_REASONING_DEADLINE_SECONDS", 90.0))
    complexity_threshold = int(getattr(app_settings, "SECONDARY_COMPLEXITY_THRESHOLD", 40))
    fast_model = getattr(app_settings, "SECONDARY_REASONING_MODEL_FAST", "gpt-4o")

    try:
        client = OpenAIClient(api_key=app_settings.OPENAI_API_KEY)  # type: ignore[arg-type]
        # Base client; actual per-attempt timeout is adjusted to fit remaining budget
        base_client = client

        # Process chunks sequentially (consider concurrency in future if rate limits allow)
        for i, chunk in enumerate(chunks):
            chunk_start_time = time.monotonic()
            # Per-chunk cache
            chunk_key = f"refine:{key_hash(chunk)}"
            cached = get_json(chunk_key)
            if isinstance(cached, list):
                logger.info("Using cached refinement for Chunk %d/%d (Size: %d).", i + 1, len(chunks), len(chunk))
                all_refined_violations.extend(cached)
                continue
            
            prompt = _build_refinement_prompt(chunk)
            
            attempt = 0
            last_err: Exception | None = None
            raw: str | None = None
            
            messages = [
                {"role": "system", "content": REFINEMENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            
            logger.info("Starting refinement for Chunk %d/%d (Size: %d)...", i + 1, len(chunks), len(chunk))
            # Resource-aware model selection
            model_to_use = app_settings.SECONDARY_REASONING_MODEL
            if len(violations) > complexity_threshold or len(chunk) >= CHUNK_SIZE:
                model_to_use = fast_model
            
            chunk_outcome = "error"  # pessimistic default
            while attempt <= max_retries:
                try:
                    # Respect remaining budget for this chunk
                    elapsed = time.monotonic() - chunk_start_time
                    remaining = max(0.0, deadline - elapsed)
                    # If essentially no time remains, stop processing further attempts for this chunk
                    if remaining < 5.0:
                        logger.error("Refinement budget exhausted for chunk %d/%d (remaining=%.2fs). Skipping chunk.", i + 1, len(chunks), remaining)
                        raw = "[]"
                        chunk_outcome = "timeout"
                        break

                    per_attempt_timeout = max(5.0, min(request_timeout, remaining - 0.5))
                    call_client = base_client.with_options(timeout=per_attempt_timeout, max_retries=0)
                    resp = call_client.chat.completions.create(  # type: ignore[attr-defined]
                        model=model_to_use,
                        messages=messages,  # type: ignore[arg-type]
                        temperature=0,
                    )
                    raw = resp.choices[0].message.content if resp.choices else "[]"
                    logger.info("Chunk %d/%d successful in %.2fs.", i + 1, len(chunks), time.monotonic() - chunk_start_time)
                    chunk_outcome = "success"
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
                        # Skip this chunk; continue others
                        raw = "[]"
                        chunk_outcome = "timeout"
                        break
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
                        raw = "[]"
                        chunk_outcome = "error"
                        break
                    time.sleep(delay)
                    attempt += 1
            
            # Post-chunk processing
            if raw is None:
                # If all retries failed for this chunk
                logger.error("Chunk %d/%d failed after all retries. Aborting refinement.", i + 1, len(chunks))
                _health.record("error")
                if _health.should_trip():
                    logger.warning("Secondary refinement unhealthy: high timeout/error ratio. Disabling for %ds.",
                                   int(getattr(app_settings, "REFINEMENT_COOLDOWN_SECONDS", 600)))
                    try:
                        _secondary_breaker.trip(int(getattr(app_settings, "REFINEMENT_COOLDOWN_SECONDS", 600)))
                    except Exception:
                        pass
                # Skip this chunk and proceed with others
                continue

            # Attempt to parse JSON and clean (tolerant extractor)
            refined = _extract_json_array(raw)
            # Record health and possibly trip breaker
            try:
                _health.record(chunk_outcome)
                if _health.should_trip():
                    logger.warning("Secondary refinement unhealthy: high timeout/error ratio. Disabling for %ds.",
                                   int(getattr(app_settings, "REFINEMENT_COOLDOWN_SECONDS", 600)))
                    _secondary_breaker.trip(int(getattr(app_settings, "REFINEMENT_COOLDOWN_SECONDS", 600)))
            except Exception:
                pass
            if isinstance(refined, list):
                # Build lookup to inherit metadata (category, regulation_ref, ids) from source items in this chunk
                source_index = []
                for src in chunk:
                    src_desc = src.get("description") or src.get("issue") or ""
                    src_key = (_norm_text(src_desc), _norm_text(src.get("contract_snippet") or src.get("contract_clause_snippet") or ""))
                    source_index.append((src_key, src))

                # Apply sanity filtering and deduplication within the chunk
                cleaned: List[Dict[str, Any]] = []
                seen_keys = set()
                for v in refined:
                    if not isinstance(v, dict):
                        continue
                    # Inherit missing fields from nearest source match
                    v_issue = v.get("issue") or v.get("description") or ""
                    v_key = (_norm_text(v_issue), _norm_text(v.get("contract_snippet") or ""))
                    for (k, src) in source_index:
                        if k == v_key:
                            # Fill category/regulation_ref/ids/snippets if missing
                            if not v.get("category"):
                                v["category"] = src.get("category")
                            if not v.get("regulation_ref"):
                                v["regulation_ref"] = src.get("regulation_ref") or src.get("regulation_reference") or src.get("reg_ref")
                            # carry through ids/snippets for grouping/instances
                            v.setdefault("contract_node_id", src.get("contract_node_id"))
                            v.setdefault("regulation_node_id", src.get("regulation_node_id"))
                            v.setdefault("regulation_snippet", src.get("regulation_snippet") or src.get("regulation_excerpt") or src.get("regulation_excerpt_snippet"))
                            break
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
                try:
                    set_json(chunk_key, cleaned)
                except Exception:
                    pass
            else:
                logger.warning("Chunk %d/%d model returned non-list JSON; discarding chunk results.", i + 1, len(chunks))
                # Do not re-raise, but skip results for this chunk

        # Final: conservative dedupe + grouping by (category, regulation_ref)
        try:
            sim_threshold = float(getattr(app_settings, "DEDUPE_SIM_THRESHOLD", 0.90))
            max_prune_ratio = float(getattr(app_settings, "MAX_PRUNE_RATIO", 0.60))
            min_items = int(getattr(app_settings, "MIN_ITEMS_AFTER_DEDUPE", 1))
        except Exception:
            sim_threshold, max_prune_ratio, min_items = 0.90, 0.60, 1

        buckets = _cluster_by_cat_reg(all_refined_violations)
        consolidated: List[Dict[str, Any]] = []
        for (cat, reg), items in buckets.items():
            consolidated.extend(_consolidate_cluster(items, sim_threshold, max_prune_ratio, min_items))

        # Build grouped view if enabled
        grouped: Dict[str, Any] = {}
        try:
            if getattr(app_settings, "GROUPING_ENABLED", True):
                group_map: DefaultDict[str, DefaultDict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
                for v in consolidated:
                    cat = v.get("category") or "Uncategorized"
                    reg = v.get("regulation_ref") or v.get("regulation_reference") or v.get("reg_ref") or "N/A"
                    group_map[str(cat)][str(reg)].append(v)
                grouped = {
                    "categories": [
                        {
                            "name": cat,
                            "regulations": [
                                {"reference": reg, "items": items}
                                for reg, items in regs.items()
                            ],
                        }
                        for cat, regs in group_map.items()
                    ]
                }
        except Exception:
            grouped = {}

        logger.info(
            "Secondary refinement processed %d violations in %d chunks, resulting in %d consolidated items.", 
            len(violations), len(chunks), len(consolidated)
        )
        _secondary_breaker.record_success()
        # Attach grouped structure for downstream consumers by placing it on a special key
        # Downstream (main/reporting) can detect presence and render if available.
        for v in consolidated:
            v.setdefault("_grouping", grouped)
        return consolidated

    except Exception as e:  # pragma: no cover - fall back path
        logger.exception("Secondary reasoning refinement failed during chunk processing; returning original violations: %s", e)
        _secondary_breaker.record_failure()
        # If any chunk fails critically, return the original list
        return violations