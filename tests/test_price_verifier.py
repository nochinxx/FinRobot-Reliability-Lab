"""
Tests for reliability_lab/verifiers/price_verifier.py.

All tests use mocked yfinance to avoid live API calls.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_price_df(prices: list[float]):
    """Build a minimal mock DataFrame matching yfinance output structure."""
    try:
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2023-01-01", periods=len(prices))
        df = pd.DataFrame({"Close": prices}, index=dates)
        return df
    except ImportError:
        return None


# ── get_return ─────────────────────────────────────────────────────────────────

class TestGetReturn:
    def test_positive_return(self, monkeypatch):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = _make_price_df([100.0, 110.0])
        import yfinance as yf
        with patch("reliability_lab.verifiers.price_verifier.yf") as mock_yf:
            mock_yf.download.return_value = df
            from reliability_lab.verifiers.price_verifier import get_return
            result = get_return("NVDA", "2023-01-01", "2023-06-01")
            assert result is not None
            assert abs(result - 0.10) < 0.001

    def test_negative_return(self):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = _make_price_df([100.0, 90.0])
        with patch("reliability_lab.verifiers.price_verifier.yf") as mock_yf:
            mock_yf.download.return_value = df
            from reliability_lab.verifiers.price_verifier import get_return
            result = get_return("TSLA", "2023-01-01", "2023-06-01")
            assert result is not None
            assert abs(result - (-0.10)) < 0.001

    def test_empty_data_returns_none(self):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = pd.DataFrame()
        with patch("reliability_lab.verifiers.price_verifier.yf") as mock_yf:
            mock_yf.download.return_value = df
            from reliability_lab.verifiers.price_verifier import get_return
            result = get_return("NVDA", "2023-01-01", "2023-06-01")
            assert result is None

    def test_zero_return(self):
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = _make_price_df([50.0, 50.0])
        with patch("reliability_lab.verifiers.price_verifier.yf") as mock_yf:
            mock_yf.download.return_value = df
            from reliability_lab.verifiers.price_verifier import get_return
            result = get_return("MSFT", "2023-01-01", "2023-06-01")
            assert result is not None
            assert abs(result) < 0.001


# ── verify_return_claim ────────────────────────────────────────────────────────

class TestVerifyReturnClaim:
    def _mock_get_return(self, actual_value):
        """Patch get_return to return a specific value."""
        return patch("reliability_lab.verifiers.price_verifier.get_return",
                     return_value=actual_value)

    def test_within_tolerance_gives_verified(self):
        with self._mock_get_return(0.20):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.21, tolerance=0.02)
            assert result["status"] == "verified"

    def test_outside_tolerance_gives_incorrect(self):
        with self._mock_get_return(0.10):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.20, tolerance=0.02)
            assert result["status"] == "incorrect"

    def test_no_data_gives_nmv(self):
        with self._mock_get_return(None):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.20)
            assert result["status"] == "not_machine_verifiable"

    def test_result_has_all_fields_on_verified(self):
        with self._mock_get_return(0.20):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.20)
            assert "status" in result
            assert "claimed" in result
            assert "actual" in result
            assert "diff" in result

    def test_exact_match_gives_zero_diff(self):
        with self._mock_get_return(0.15):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.15)
            assert result["diff"] == 0.0
            assert result["status"] == "verified"

    def test_default_tolerance_is_two_percent(self):
        # At 2.1% diff, should be incorrect with default tolerance
        with self._mock_get_return(0.10):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.121)
            assert result["status"] == "incorrect"

    def test_at_exactly_tolerance_boundary(self):
        # diff = exactly 0.02 → should be verified (≤ tolerance)
        with self._mock_get_return(0.10):
            from reliability_lab.verifiers.price_verifier import verify_return_claim
            result = verify_return_claim("NVDA", "2023-01-01", "2023-06-01",
                                         claimed_return=0.12, tolerance=0.02)
            assert result["status"] == "verified"
