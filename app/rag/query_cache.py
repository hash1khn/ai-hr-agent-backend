from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

from app.config import get_settings

_CACHE: dict[str, "_Entry"] = {}
_TTL_SECONDS = 15 * 60
_MAX_ENTRIES = 500


@dataclass
class _Entry:
    value: object
    expires_at: float


def normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def make_key(
    company_id: str,
    role: str,
    query: str,
    history: str,
    index_version: str,
) -> str:
    settings = get_settings()
    material = "|".join(
        [
            str(company_id),
            str(role),
            normalize_query(query),
            normalize_query(history),
            str(settings.retrieve_top_k),
            str(settings.similarity_floor),
            settings.embedding_model,
            settings.chat_model,
            index_version,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def get(key: str):
    entry = _CACHE.get(key)
    if not entry:
        return None
    if entry.expires_at <= time.time():
        _CACHE.pop(key, None)
        return None
    return entry.value


def set_value(key: str, value: object) -> None:
    if len(_CACHE) >= _MAX_ENTRIES:
        oldest = min(_CACHE, key=lambda item: _CACHE[item].expires_at)
        _CACHE.pop(oldest, None)
    _CACHE[key] = _Entry(value=value, expires_at=time.time() + _TTL_SECONDS)


def clear() -> None:
    _CACHE.clear()
