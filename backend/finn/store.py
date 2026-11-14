"""Tiny JSON file cache with a TTL and a committed-snapshot fallback."""
import json
import re
import time
from pathlib import Path

from .config import CACHE, OFFLINE, SNAPSHOT


def _safe(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def read(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1))
    tmp.replace(path)


def cached(key: str, ttl_seconds: float, fetch):
    """Return a fresh cache entry, else fetch; on fetch failure fall back to stale cache, then snapshot.

    The result is (value, source) where source is 'live', 'cache', 'stale' or 'snapshot'.
    """
    if OFFLINE:
        value = read(SNAPSHOT / f"{_safe(key)}.json")
        if value is not None:
            return value, "snapshot"
    path = CACHE / f"{_safe(key)}.json"
    if path.exists() and time.time() - path.stat().st_mtime < ttl_seconds:
        value = read(path)
        if value is not None:
            return value, "cache"
    try:
        value = fetch()
        write(path, value)
        return value, "live"
    except Exception:
        value = read(path)
        if value is not None:
            return value, "stale"
        value = read(SNAPSHOT / f"{_safe(key)}.json")
        if value is not None:
            return value, "snapshot"
        raise
