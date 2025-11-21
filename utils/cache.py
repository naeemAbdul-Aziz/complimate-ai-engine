import hashlib
import json
import os
import threading
import time
from typing import Any, Optional, Dict
from dataclasses import dataclass

# --- Advanced Caching Configuration ---

@dataclass
class CacheStats:
    """Track cache performance metrics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "evictions": self.evictions
        }

# Global stats tracking
_stats = CacheStats()

# Tiered TTL configuration (in seconds)
TTL_TIERS = {
    "regulation": 7200,      # 2 hours - regulations change rarely
    "retrieval": 3600,       # 1 hour - retrieval results
    "primary": 1800,         # 30 min - LLM responses
    "pdf_text": 86400 * 30,  # 30 days - extracted text rarely changes
    "default": 900           # 15 min - everything else
}

# Fine-grained locking
_locks: Dict[str, threading.Lock] = {
    "memory": threading.Lock(),
    "stats": threading.Lock()
}

_memory_store: dict[str, tuple[float, str]] = {}

_redis = None
_redis_available = False
_default_ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

try:
    from redis import Redis  # type: ignore
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        _redis = Redis.from_url(_redis_url)
        _redis_available = True
except Exception:
    _redis = None
    _redis_available = False


def key_hash(obj: Any) -> str:
    try:
        payload = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    except TypeError:
        payload = str(obj).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_json(key: str) -> Optional[Any]:
    """Get item from cache with metrics tracking."""
    # Try Redis first
    if _redis_available and _redis is not None:
        try:
            data = _redis.get(key)
            if data:
                with _locks["stats"]:
                    _stats.hits += 1
                return json.loads(data)
        except Exception:
            pass

    # Fallback memory
    now = time.time()
    with _locks["memory"]:
        entry = _memory_store.get(key)
        if not entry:
            with _locks["stats"]:
                _stats.misses += 1
            return None
            
        exp, data = entry
        if exp and exp < now:
            _memory_store.pop(key, None)
            with _locks["stats"]:
                _stats.misses += 1
                _stats.evictions += 1
            return None
            
        try:
            val = json.loads(data)
            with _locks["stats"]:
                _stats.hits += 1
            return val
        except Exception:
            with _locks["stats"]:
                _stats.misses += 1
            return None


def set_json(key: str, value: Any, ttl: Optional[int] = None, tier: str = "default") -> None:
    """Set item in cache with tiered TTL support."""
    # Determine TTL based on tier if not explicitly provided
    if ttl is None:
        ttl = TTL_TIERS.get(tier, TTL_TIERS["default"])
        
    data = json.dumps(value, ensure_ascii=False)
    
    # Try Redis first
    if _redis_available and _redis is not None:
        try:
            _redis.setex(key, ttl, data)
            return
        except Exception:
            pass
            
    # Fallback memory
    # 0 means no expiration for memory cache (or very long)
    # For safety in memory, we still set a max limit or rely on LRU in future
    # Here we just use the timestamp
    exp = time.time() + ttl
    
    with _locks["memory"]:
        # Simple size protection for memory cache
        if len(_memory_store) > 10000:
            # Random eviction of 10% items to prevent OOM
            # (A real LRU would be better but this is a quick safety valve)
            keys = list(_memory_store.keys())[:1000]
            for k in keys:
                _memory_store.pop(k, None)
            with _locks["stats"]:
                _stats.evictions += 1000
                
        _memory_store[key] = (exp, data)

def get_cache_stats() -> Dict[str, Any]:
    """Return current cache statistics."""
    with _locks["stats"]:
        return _stats.to_dict()
