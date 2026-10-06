import time
from collections import defaultdict, deque
from fastapi import HTTPException

_hits: dict[str, deque] = defaultdict(deque)

def limit(key: str, max_hits: int, window_seconds: int) -> None:
    """Small in-memory limiter (per server process). Raises 429 when a key is used too often."""
    now = time.monotonic()
    if len(_hits) > 20000:
        for k in [k for k, q in _hits.items() if not q or now - q[-1] > window_seconds]:
            _hits.pop(k, None)
    q = _hits[key]
    while q and now - q[0] > window_seconds:
        q.popleft()
    if len(q) >= max_hits:
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")
    q.append(now)
