from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException


_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str, *, limit: int = 30, window_seconds: int = 60) -> None:
    now = monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] >= window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(429, "Rate limit exceeded; please retry later")
    bucket.append(now)
