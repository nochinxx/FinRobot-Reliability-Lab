"""
Tests for backtest_signal.py — signal extraction from claims.
All tests use inline fixture data; no live API calls, no yfinance.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import backtest_signal


# ── extract_signal ─────────────────────────────────────────────────────────────

def _write_fixtures(tmp_path: Path, claims: list[dict], scorecard: dict) -> str:
    ticker = "NVDA"
    ticker_dir = tmp_path / ticker
    ticker_dir.mkdir()
    (ticker_dir / f"{ticker}_claims.json").write_text(json.dumps(claims))
    (ticker_dir / f"{ticker}_reliability_scorecard.json").write_text(json.dumps(scorecard))
    return ticker


_SCORECARD = {
    "metrics": {
        "incorrect_claim_rate": 0.36,
        "source_coverage_rate": 0.34,
        "valuation_dispersion": 0.484,
    }
}


class TestExtractSignal:
    def test_buy_signal_when_target_above_current(self, tmp_path):
        claims = [
            {"claim_text": "Target $200 with current Price $150 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert result["signal"] == "buy"
        assert result["target_price"] == 200.0
        assert result["current_price"] == 150.0

    def test_hold_signal_when_target_near_current(self, tmp_path):
        claims = [
            {"claim_text": "Target $152 with current Price $150 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert result["signal"] == "hold"  # < 5% upside

    def test_upside_pct_computed(self, tmp_path):
        claims = [
            {"claim_text": "Target $200 with current Price $100 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert abs(result["upside_pct"] - 100.0) < 0.01

    def test_icr_scr_vd_extracted(self, tmp_path):
        claims = [
            {"claim_text": "Target $200 with current Price $150 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert result["icr"] == pytest.approx(0.36, abs=0.001)
        assert result["scr"] == pytest.approx(0.34, abs=0.001)
        assert result["vd"] == pytest.approx(0.484, abs=0.001)

    def test_missing_files_returns_none(self, tmp_path):
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal("NONEXISTENT")
        assert result is None

    def test_report_date_extracted_from_claims(self, tmp_path):
        claims = [
            {"claim_text": "Report dated March 15, 2026 Target $200 Price $150",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert result["report_date"] == "2026-03-15"

    def test_no_price_data_returns_none(self, tmp_path):
        claims = [
            {"claim_text": "This claim has no price information whatsoever",
             "claim_type": "narrative", "metric": "financial_figure"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is None

    def test_ticker_preserved_in_result(self, tmp_path):
        claims = [
            {"claim_text": "Target $200 with current Price $150 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        assert result["ticker"] == "NVDA"

    def test_all_required_fields_present(self, tmp_path):
        claims = [
            {"claim_text": "Target $200 with current Price $150 in March 2026",
             "claim_type": "valuation", "metric": "price_target"},
        ]
        ticker = _write_fixtures(tmp_path, claims, _SCORECARD)
        with patch.object(backtest_signal, "OUTPUT_DIR", tmp_path):
            result = backtest_signal.extract_signal(ticker)
        assert result is not None
        for field in ("ticker", "report_date", "current_price", "target_price",
                      "upside_pct", "signal", "icr", "scr"):
            assert field in result, f"Missing field: {field}"


# ── get_returns (offline — tests behavior when yfinance unavailable) ────────────

class TestGetReturnsOffline:
    def test_returns_none_when_yfinance_unavailable(self):
        with patch.object(backtest_signal, "YFINANCE", False):
            result = backtest_signal.get_returns("NVDA", "2023-01-01")
        assert result["return_current"] is None
        assert result["return_6m"] is None
        assert result["return_1y"] is None
