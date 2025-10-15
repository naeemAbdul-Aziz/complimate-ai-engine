# Performance, Reliability, and Security Knobs

This guide documents the runtime knobs we added to keep latency bounded, reduce cost via caching, and improve safety when calling external LLMs.

## Summary
- Layered caching (retrieval, primary prompts, refinement chunks)
- Tolerant JSON extraction and fail-open behavior
- Circuit breaker for secondary refinement
- Prompt scrubbing to minimize PII
- Time-bounded, chunked secondary refinement with adaptive model selection

## Environment Variables

Core models
- OPENAI_MODEL: primary extraction model (default: gpt-4.1)
- OPENAI_EMBEDDING_MODEL: embedding model (default: text-embedding-3-large)
- SECONDARY_REASONING_MODEL: secondary refinement model (default: gpt-4.1)
- ENABLE_SECONDARY_REASONING: True|False to enable refinement (default: True)

Timeouts and retries
- OPENAI_REQUEST_TIMEOUT: LlamaIndex request timeout for primary model (default: 180.0)
- OPENAI_MAX_RETRIES: Primary model retries (default: 3)
- SECONDARY_REASONING_REQUEST_TIMEOUT: Per-call timeout for refinement (default: 60)
- SECONDARY_REASONING_DEADLINE_SECONDS: Hard per-chunk deadline (default: 90)
- SECONDARY_REASONING_MAX_RETRIES: Attempts per chunk (default: 1)

Refinement adaptivity
- SECONDARY_COMPLEXITY_THRESHOLD: threshold to switch to fast model (default: 40)
- SECONDARY_REASONING_MODEL_FAST: fast model when input is complex/large (default: gpt-4o)

Circuit breaker
- SECONDARY_BREAKER_FAIL_THRESHOLD: consecutive failures before opening breaker (default: 2)
- SECONDARY_BREAKER_RESET_SECONDS: cooldown (default: 300)

Caching
- REDIS_URL: enable Redis-backed cache if set; otherwise in-memory fallback
- CACHE_TTL_SECONDS: TTL for cached JSON payloads (default: 3600)

Retrieval
- HYBRID_SEARCH_TOP_K: BM25+vector top K (default: 5)

WebSockets
- ENABLE_WEBSOCKETS: enable realtime progress (default: True)
- MAX_WS_CONNECTIONS: cap connections (default: 100)

## Caching Layers
- Retrieval cache: caches regulation search per contract node to avoid repeated BM25/vector lookups.
- Primary prompt cache: caches parsed violation arrays keyed by prompt+regNode; main CLI merges cached results and skips LLM calls on hit.
- Refinement per-chunk cache: caches chunked refinement results to avoid reprocessing.

## Prompt Scrubbing
We scrub emails, phone numbers, and ID/account-like tokens before sending prompts to the LLM. This reduces PII exposure and helps keep prompts short and stable.

## Failure Modes
- Primary extraction: errors are captured per request; analysis proceeds with available results.
- Refinement: bounded by per-call timeout and per-chunk deadline. On repeated failures, the circuit breaker opens and refinement is skipped temporarily.
- JSON output: tolerant extractor recovers arrays from noisy responses; falls back to original candidates on failure.

## Ops Tips
- For throughput, consider OPENAI_MODEL=gpt-4o and keep refinement at gpt-4.1.
- If latency spikes, decrease HYBRID_SEARCH_TOP_K or disable secondary refinement temporarily.
- Use Redis in production for cache size and eviction control.
- Keep reports/ and vector_store/ on fast local disks or provision adequate IOPS in containers.
