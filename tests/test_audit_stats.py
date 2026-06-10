"""
Tests for reliability_lab/statistics/audit_stats.py.
ICR decomposition, coverage analysis, ICR-alpha correlation.
No live API calls — uses inline data and existing snapshot fixtures.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.statistics.audit_stats import (
    classify_incorrect_claim,
    decompose_icr,
    aggregate_decomposition,
    icr_alpha_correlation,
    coverage_summary,
    FORWARD_YEAR_CUTOFF,
    GROWTH_ARTIFACT_METRICS,
    GROWTH_ARTIFACT_PERIODS,
)


# ── classify_incorrect_claim ───────────────────────────────────────────────────

class TestClassifyIncorrectClaim:
    def test_forward_2025(self):
        row = {"metric": "ebitda_margin", "period": "2025"}
        assert classify_incorrect_claim(row) == "forward_projection"

    def test_forward_future_year(self):
        row = {"metric": "revenue", "period": "2026"}
        assert classify_incorrect_claim(row) == "forward_projection"

    def test_growth_artifact_2021(self):
        row = {"metric": "revenue_growth", "period": "2021"}
        assert classify_incorrect_claim(row) == "growth_misattribution"

    def test_growth_artifact_2022(self):
        row = {"metric": "revenue_growth", "period": "2022"}
        assert classify_incorrect_claim(row) == "growth_misattribution"

    def test_ebitda_margin_2021_is_artifact(self):
        row = {"metric": "ebitda_margin", "period": "2021"}
        assert classify_incorrect_claim(row) == "growth_misattribution"

    def test_revenue_2021_is_genuine(self):
        # revenue in 2021 is NOT a growth metric → genuine error
        row = {"metric": "revenue", "period": "2021"}
        assert classify_incorrect_claim(row) == "genuine_error"

    def test_pe_ratio_2023_is_genuine(self):
        row = {"metric": "pe_ratio", "period": "2023"}
        assert classify_incorrect_claim(row) == "genuine_error"

    def test_ev_ebitda_2024_is_genuine(self):
        row = {"metric": "ev_ebitda", "period": "2024"}
        assert classify_incorrect_claim(row) == "genuine_error"

    def test_empty_period_is_genuine(self):
        row = {"metric": "revenue", "period": ""}
        assert classify_incorrect_claim(row) == "genuine_error"

    def test_growth_artifact_only_in_artifact_periods(self):
        # revenue_growth in 2023 is NOT an artifact period → genuine
        row = {"metric": "revenue_growth", "period": "2023"}
        assert classify_incorrect_claim(row) == "genuine_error"


# ── decompose_icr ──────────────────────────────────────────────────────────────

def _make_rows(statuses: list[str], metrics: list[str] = None, periods: list[str] = None):
    metrics  = metrics  or ["revenue"] * len(statuses)
    periods  = periods  or ["2023"] * len(statuses)
    return [
        {"verification_status": s, "metric": m, "period": p}
        for s, m, p in zip(statuses, metrics, periods)
    ]


class TestDecomposeICR:
    def test_empty_rows(self):
        result = decompose_icr([])
        assert result["total_incorrect"] == 0
        assert result["icr"] == 0.0

    def test_no_incorrect(self):
        rows = _make_rows(["verified", "verified", "not_machine_verifiable"])
        result = decompose_icr(rows)
        assert result["total_incorrect"] == 0
        assert result["adjusted_icr"] == 0.0

    def test_forward_projection_classified(self):
        rows = _make_rows(["incorrect"], ["ebitda_margin"], ["2025"])
        result = decompose_icr(rows)
        assert result["categories"]["forward_projection"]["n"] == 1
        assert result["categories"]["genuine_error"]["n"] == 0

    def test_growth_artifact_classified(self):
        rows = _make_rows(["incorrect"], ["revenue_growth"], ["2021"])
        result = decompose_icr(rows)
        assert result["categories"]["growth_misattribution"]["n"] == 1

    def test_genuine_error_classified(self):
        rows = _make_rows(["incorrect"], ["pe_ratio"], ["2023"])
        result = decompose_icr(rows)
        assert result["categories"]["genuine_error"]["n"] == 1

    def test_icr_computed_correctly(self):
        rows = _make_rows(["verified", "incorrect", "incorrect"])
        result = decompose_icr(rows)
        assert result["machine_verifiable"] == 3
        assert result["icr"] == pytest.approx(2 / 3, abs=0.001)

    def test_adjusted_icr_excludes_artifacts(self):
        rows = [
            {"verification_status": "verified",  "metric": "revenue",       "period": "2023"},
            {"verification_status": "incorrect", "metric": "revenue_growth", "period": "2021"},  # artifact
            {"verification_status": "incorrect", "metric": "pe_ratio",       "period": "2023"},  # genuine
        ]
        result = decompose_icr(rows)
        # ICR = 2/3; adjusted_icr = 1/3 (only genuine error)
        assert result["icr"] == pytest.approx(2 / 3, abs=0.001)
        assert result["adjusted_icr"] == pytest.approx(1 / 3, abs=0.001)

    def test_mixed_categories(self):
        rows = [
            {"verification_status": "incorrect", "metric": "ebitda_margin",  "period": "2025"},  # forward
            {"verification_status": "incorrect", "metric": "revenue_growth",  "period": "2021"},  # artifact
            {"verification_status": "incorrect", "metric": "ev_ebitda",       "period": "2023"},  # genuine
            {"verification_status": "verified",  "metric": "revenue",         "period": "2023"},
        ]
        result = decompose_icr(rows)
        cats = result["categories"]
        assert cats["forward_projection"]["n"] == 1
        assert cats["growth_misattribution"]["n"] == 1
        assert cats["genuine_error"]["n"] == 1
        assert result["total_incorrect"] == 3


# ── aggregate_decomposition ───────────────────────────────────────────────────

class TestAggregateDecomposition:
    def test_missing_ticker_skipped(self, tmp_path):
        result = aggregate_decomposition(["NOTEXIST"], output_dir=str(tmp_path))
        assert result["aggregate"]["total_incorrect"] == 0

    def test_single_ticker_csv(self, tmp_path):
        from reliability_lab.fact_table_builder import FACT_TABLE_COLUMNS
        ticker_dir = tmp_path / "NVDA"
        ticker_dir.mkdir()
        csv_path = ticker_dir / "NVDA_fact_table.csv"
        rows = [
            {c: "" for c in FACT_TABLE_COLUMNS},
            {c: "" for c in FACT_TABLE_COLUMNS},
        ]
        rows[0].update({"verification_status": "incorrect", "metric": "revenue_growth", "period": "2021"})
        rows[1].update({"verification_status": "verified",  "metric": "revenue", "period": "2023"})
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FACT_TABLE_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        result = aggregate_decomposition(["NVDA"], output_dir=str(tmp_path))
        agg = result["aggregate"]
        assert agg["total_incorrect"] == 1
        assert agg["categories"]["growth_misattribution"] == 1
        assert agg["categories"]["genuine_error"] == 0


# ── coverage_summary ──────────────────────────────────────────────────────────

class TestCoverageSummary:
    def test_missing_tickers_empty(self, tmp_path):
        result = coverage_summary(["NOTEXIST"], output_dir=str(tmp_path))
        assert result == {}

    def test_single_ticker_scorecard(self, tmp_path):
        ticker_dir = tmp_path / "NVDA"
        ticker_dir.mkdir()
        sc = {
            "summary": {"total_claims": 100, "machine_verifiable_claims": 30,
                         "verified_count": 20, "incorrect_count": 10,
                         "unsupported_count": 10, "not_machine_verifiable": 60},
            "metrics": {"source_coverage_rate": 0.30, "incorrect_claim_rate": 0.33,
                         "primary_source_coverage_rate": 0.67, "unsupported_claim_rate": 0.10,
                         "valuation_dispersion": 0.45},
        }
        (ticker_dir / "NVDA_reliability_scorecard.json").write_text(json.dumps(sc))
        result = coverage_summary(["NVDA"], output_dir=str(tmp_path))
        assert result["aggregate"]["total_claims"] == 100
        assert result["aggregate"]["aggregate_scr"] == pytest.approx(0.30, abs=0.01)


# ── icr_alpha_correlation ─────────────────────────────────────────────────────

SNAP_DIR = Path("output/historical_backtest")
ICR_VALUES = {
    "NVDA": 0.361, "TSLA": 0.603, "META": 0.581, "MSFT": 0.714, "COP": 0.800,
    "ETSY": 0.778, "ROKU": 1.000, "RIVN": 0.471, "RBLX": 1.000, "LCID": 0.667,
}


@pytest.mark.skipif(not SNAP_DIR.exists(), reason="No backtest snapshots")
class TestICRAlphaCorrelation:
    def test_returns_n_27(self):
        result = icr_alpha_correlation(
            list(ICR_VALUES.keys()), ICR_VALUES,
            snapshot_dir=str(SNAP_DIR), horizon="6m"
        )
        assert result.get("n") == 27

    def test_spearman_rho_in_range(self):
        result = icr_alpha_correlation(
            list(ICR_VALUES.keys()), ICR_VALUES,
            snapshot_dir=str(SNAP_DIR), horizon="6m"
        )
        rho = result.get("spearman_rho")
        if rho is not None:
            assert -1.0 <= rho <= 1.0

    def test_not_significant(self):
        result = icr_alpha_correlation(
            list(ICR_VALUES.keys()), ICR_VALUES,
            snapshot_dir=str(SNAP_DIR), horizon="6m"
        )
        if result.get("significant_0.05") is not None:
            assert result["significant_0.05"] is False  # known non-significant result

    def test_within_buy_computed(self):
        result = icr_alpha_correlation(
            list(ICR_VALUES.keys()), ICR_VALUES,
            snapshot_dir=str(SNAP_DIR), horizon="6m"
        )
        assert "within_buy_rho" in result
        assert result["within_buy_n"] == 9

    def test_empty_icr_returns_error(self, tmp_path):
        result = icr_alpha_correlation(
            [], {}, snapshot_dir=str(tmp_path), horizon="6m"
        )
        assert "error" in result or result.get("n", 0) < 4
