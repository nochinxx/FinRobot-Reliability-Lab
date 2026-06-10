"""
Centralized persistent cache for all external API calls (FMP, SEC EDGAR).

Environment controls:
  DEV_MODE=1    — cache-only; return None on miss (soft fail, no API calls)
  OFFLINE=1     — cache-only; raise CacheMissError on miss (hard fail for tests)

Both modes protect the FMP 250-call/day quota and allow fully offline development.
Neither mode is set in production — omit both env vars for live operation.

Cache layout:
  reliability_lab/output/api_cache/fmp/{endpoint}_{symbol}.json   (TTL: 24h)
  reliability_lab/output/api_cache/sec/{cik}.json                 (TTL: 7 days)
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

_CACHE_ROOT = Path(__file__).parent.parent / "output" / "api_cache"
_FMP_TTL  = 86_400       # 24 hours
_SEC_TTL  = 7 * 86_400   # 7 days (company facts change rarely)


class CacheMissError(Exception):
    """Raised in OFFLINE=1 mode when a cache miss would require a live API call."""


def _dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").strip() in ("1", "true", "yes")


def _offline_mode() -> bool:
    return os.environ.get("OFFLINE", "").strip() in ("1", "true", "yes")


def _cache_path(namespace: str, key: str) -> Path:
    p = _CACHE_ROOT / namespace
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def cache_get(namespace: str, key: str, ttl: int) -> Optional[Any]:
    """Return cached value if it exists and is within TTL, else None."""
    p = _cache_path(namespace, key)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def cache_set(namespace: str, key: str, value: Any) -> None:
    """Write value to cache."""
    try:
        _cache_path(namespace, key).write_text(json.dumps(value))
    except OSError:
        pass


def cache_status() -> dict:
    """Return a summary of all cached entries (for cache_manager.py)."""
    if not _CACHE_ROOT.exists():
        return {}
    result = {}
    for ns_dir in _CACHE_ROOT.iterdir():
        if not ns_dir.is_dir():
            continue
        ns = ns_dir.name
        result[ns] = {}
        for f in ns_dir.glob("*.json"):
            age_h = (time.time() - f.stat().st_mtime) / 3600
            ttl = _FMP_TTL if ns == "fmp" else _SEC_TTL
            result[ns][f.stem] = {
                "age_hours": round(age_h, 1),
                "stale": age_h * 3600 > ttl,
                "size_kb": round(f.stat().st_size / 1024, 1),
            }
    return result


def fmp_get(endpoint: str, symbol: str, fetch_fn) -> Optional[list]:
    """
    Cache-aware FMP fetch.
    fetch_fn: callable() → list  (the actual HTTP call, no args needed)

    Workflow:
      1. Check cache → return if fresh hit
      2. If DEV_MODE or OFFLINE → return None (or raise) on miss
      3. Otherwise call fetch_fn(), cache result, return it
    """
    key = f"{endpoint.replace('/', '_')}_{symbol}"
    cached = cache_get("fmp", key, _FMP_TTL)
    if cached is not None:
        return cached

    if _offline_mode():
        raise CacheMissError(f"FMP cache miss in OFFLINE mode: {endpoint} {symbol}")
    if _dev_mode():
        return None  # soft fail — verifier returns not_machine_verifiable

    data = fetch_fn()
    if data:
        cache_set("fmp", key, data)
    return data or []


def sec_get(cik: str, fetch_fn) -> Optional[dict]:
    """
    Cache-aware SEC EDGAR company facts fetch.
    fetch_fn: callable() → dict
    """
    cached = cache_get("sec", cik, _SEC_TTL)
    if cached is not None:
        return cached

    if _offline_mode():
        raise CacheMissError(f"SEC cache miss in OFFLINE mode: CIK {cik}")
    if _dev_mode():
        return None

    data = fetch_fn()
    if data:
        cache_set("sec", cik, data)
    return data
