import hashlib
import json
import os
import threading
import time
from typing import Any, Optional

_lock = threading.Lock()
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
    # Try Redis first
    if _redis_available and _redis is not None:
        try:
            data = _redis.get(key)
            if data is None:
                return None
            return json.loads(data)
        except Exception:
            pass
    # Fallback memory
    now = time.time()
    with _lock:
        entry = _memory_store.get(key)
        if not entry:
            return None
        exp, data = entry
        if exp and exp < now:
            _memory_store.pop(key, None)
            return None
        try:
            return json.loads(data)
        except Exception:
            return None


def set_json(key: str, value: Any, ttl: Optional[int] = None) -> None:
    ttl = ttl or _default_ttl
    data = json.dumps(value, ensure_ascii=False)
    # Try Redis first
    if _redis_available and _redis is not None:
        try:
            _redis.setex(key, ttl, data)
            return
        except Exception:
            pass
    # Fallback memory
    exp = time.time() + ttl if ttl else 0
    with _lock:
        _memory_store[key] = (exp, data)
