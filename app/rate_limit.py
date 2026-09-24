from __future__ import annotations

from collections import defaultdict, deque
from time import time

from fastapi import HTTPException, Request

from app.config import get_settings
from app.security import extract_token


_hits: dict[str, deque[float]] = defaultdict(deque)
_last_sweep = time()
_SWEEP_INTERVAL_SECONDS = 60.0
_WINDOW_SECONDS = 60.0


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "anon"


def _sweep_stale(now: float) -> None:
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep = now
    stale = [key for key, window in _hits.items() if not window or now - window[-1] > _WINDOW_SECONDS]
    for key in stale:
        _hits.pop(key, None)


def enforce_rate_limit(key: str, limit: int, detail: str) -> None:
    now = time()
    _sweep_stale(now)
    window = _hits[key]
    while window and now - window[0] > _WINDOW_SECONDS:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail=detail)
    window.append(now)


def enforce_chat_rate_limit(request: Request) -> None:
    settings = get_settings()
    token = extract_token(request) or _client_ip(request)
    key = f"chat:{str(token)[:80]}"
    enforce_rate_limit(
        key,
        settings.chat_rate_limit_per_minute,
        "Too many chat requests. Please wait a moment and try again.",
    )


def enforce_auth_rate_limit(request: Request) -> None:
    settings = get_settings()
    key = f"auth:{_client_ip(request)}"
    enforce_rate_limit(
        key,
        settings.auth_rate_limit_per_minute,
        "Too many login attempts. Please wait a moment and try again.",
    )
