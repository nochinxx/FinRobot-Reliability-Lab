"""
Tests for reliability_lab/verifiers/api_cache.py.
DEV_MODE behavior, OFFLINE mode, cache hit/miss, fmp_get/sec_get logic.
"""
import json
import os
import time
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── cache_get / cache_set ──────────────────────────────────────────────────────

class TestCacheGetSet:
    def test_cache_miss_returns_none(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_get
            result = cache_get("fmp", "test_key", ttl=3600)
        assert result is None

    def test_cache_hit_returns_value(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_get, cache_set
            cache_set("fmp", "test_key", [{"value": 42}])
            result = cache_get("fmp", "test_key", ttl=3600)
        assert result == [{"value": 42}]

    def test_stale_cache_returns_none(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_get, cache_set, _cache_path
            cache_set("fmp", "stale_key", [1, 2, 3])
            # Backdate file mtime to simulate expiry
            p = _cache_path("fmp", "stale_key")
            old_time = time.time() - 90_000  # 25 hours ago
            os.utime(p, (old_time, old_time))
            result = cache_get("fmp", "stale_key", ttl=86_400)
        assert result is None

    def test_cache_set_creates_file(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_set, _cache_path
            cache_set("sec", "0001045810", {"facts": {}})
            p = _cache_path("sec", "0001045810")
        assert p.exists()

    def test_cache_different_namespaces_isolated(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_get, cache_set
            cache_set("fmp", "key1", "fmp_data")
            result_sec = cache_get("sec", "key1", ttl=3600)
        assert result_sec is None

    def test_malformed_json_returns_none(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_get, _cache_path
            ns_dir = tmp_path / "fmp"
            ns_dir.mkdir()
            (ns_dir / "bad_key.json").write_text("{not valid json")
            result = cache_get("fmp", "bad_key", ttl=3600)
        assert result is None


# ── DEV_MODE behavior ─────────────────────────────────────────────────────────

class TestDevMode:
    def test_dev_mode_returns_none_on_miss(self, tmp_path):
        from reliability_lab.verifiers import api_cache
        import importlib; importlib.reload(api_cache)
        with patch.dict(os.environ, {"DEV_MODE": "1"}), \
             patch.object(api_cache, "_CACHE_ROOT", tmp_path):
            fetch_called = []
            def fetch(): fetch_called.append(1); return [{"data": "live"}]
            result = api_cache.fmp_get("ratios", "NVDA", fetch)
        assert result is None
        assert fetch_called == [], "fetch_fn should not be called in DEV_MODE"

    def test_dev_mode_cache_hit_still_returns(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path), \
             patch.dict(os.environ, {"DEV_MODE": "1"}):
            from reliability_lab.verifiers import api_cache
            import importlib; importlib.reload(api_cache)
            # Pre-populate cache
            api_cache.cache_set("fmp", "ratios_NVDA", [{"priceToEarningsRatio": 39.9}])
            result = api_cache.fmp_get("ratios", "NVDA", lambda: [])
        assert result is not None
        assert result[0]["priceToEarningsRatio"] == 39.9


# ── OFFLINE mode ──────────────────────────────────────────────────────────────

class TestOfflineMode:
    def test_offline_mode_raises_on_miss(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path), \
             patch.dict(os.environ, {"OFFLINE": "1", "DEV_MODE": "0"}):
            from reliability_lab.verifiers import api_cache
            import importlib; importlib.reload(api_cache)
            with pytest.raises(api_cache.CacheMissError):
                api_cache.fmp_get("ratios", "AAPL", lambda: [])


# ── fmp_get ───────────────────────────────────────────────────────────────────

class TestFmpGet:
    def test_calls_fetch_fn_on_miss(self, tmp_path):
        from reliability_lab.verifiers import api_cache
        import importlib; importlib.reload(api_cache)
        with patch.dict(os.environ, {"DEV_MODE": "0", "OFFLINE": "0"}), \
             patch.object(api_cache, "_CACHE_ROOT", tmp_path):
            called = []
            def fetch(): called.append(1); return [{"val": 1}]
            result = api_cache.fmp_get("key-metrics", "TSLA", fetch)
        assert called == [1]
        assert result == [{"val": 1}]

    def test_caches_result_after_fetch(self, tmp_path):
        from reliability_lab.verifiers import api_cache
        import importlib; importlib.reload(api_cache)
        with patch.dict(os.environ, {"DEV_MODE": "0", "OFFLINE": "0"}), \
             patch.object(api_cache, "_CACHE_ROOT", tmp_path):
            call_count = [0]
            def fetch(): call_count[0] += 1; return [{"val": 99}]
            api_cache.fmp_get("ratios", "META", fetch)
            api_cache.fmp_get("ratios", "META", fetch)  # second call should hit cache
        assert call_count[0] == 1, "fetch_fn should only be called once"

    def test_returns_empty_list_when_fetch_returns_empty(self, tmp_path):
        from reliability_lab.verifiers import api_cache
        import importlib; importlib.reload(api_cache)
        with patch.dict(os.environ, {"DEV_MODE": "0", "OFFLINE": "0"}), \
             patch.object(api_cache, "_CACHE_ROOT", tmp_path):
            result = api_cache.fmp_get("ratios", "XYZ", lambda: [])
        assert result == []


# ── cache_status ──────────────────────────────────────────────────────────────

class TestCacheStatus:
    def test_empty_cache_returns_empty_dict(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_status
            result = cache_status()
        assert result == {}

    def test_nonexistent_cache_dir_returns_empty(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", nonexistent):
            from reliability_lab.verifiers.api_cache import cache_status
            result = cache_status()
        assert result == {}

    def test_populated_cache_shows_entry(self, tmp_path):
        with patch("reliability_lab.verifiers.api_cache._CACHE_ROOT", tmp_path):
            from reliability_lab.verifiers.api_cache import cache_set, cache_status
            cache_set("fmp", "ratios_NVDA", [{"val": 1}])
            result = cache_status()
        assert "fmp" in result
        assert "ratios_NVDA" in result["fmp"]
        assert "age_hours" in result["fmp"]["ratios_NVDA"]
        assert "stale" in result["fmp"]["ratios_NVDA"]
