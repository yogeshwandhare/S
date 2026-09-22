"""
Minimal in-process sliding-window rate limiter for the login endpoint.

This is intentionally simple: it is per-process state, which is correct for
the single-worker deployment documented in the README (`uvicorn` with one
worker, scaled via multiple containers behind Caddy only if the operator
adds shared storage). It is not a substitute for a real distributed limiter
(e.g. Redis-backed) in a multi-worker production deployment -- that
limitation is called out in docs/LIMITATIONS.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import get_settings

settings = get_settings()

_attempts: dict[str, deque[float]] = defaultdict(deque)


def is_rate_limited(key: str) -> bool:
    now = time.monotonic()
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    bucket = _attempts[key]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    return len(bucket) >= settings.LOGIN_RATE_LIMIT_ATTEMPTS


def record_attempt(key: str) -> None:
    _attempts[key].append(time.monotonic())


def reset(key: str) -> None:
    _attempts.pop(key, None)


def reset_all() -> None:
    """Clear all rate-limit state. Used by the test suite to isolate tests
    from each other; never called from application request-handling code."""
    _attempts.clear()
