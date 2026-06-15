"""
Fixture-based unit tests for reliability_lab/reliability_metrics.py.

No live API calls. Tests use inline fact rows and the sample_scorecard.json fixture.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.reliability_metrics import compute_scorecard

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_SCORECARD = FIXTURES / "sample_scorecard.json"
SAMPLE_FACT_TABLE = FIXTURES / "sample_fact_table.csv"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(status, metric="revenue", claimed="$10B"):
    return {"verification_status": status, "metric": metric, "claimed_value": claimed}


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_zero_claims(self):
        result = compute_scorecard([])
        assert "error" in result

    def test_all_verified(self):
        rows = [_row("verified") for _ in range(4)]
        sc = compute_scorecard(rows)
        assert sc["summary"]["verified_count"] == 4
        assert sc["summary"]["incorrect_count"] == 0
        assert sc["metrics"]["incorrect_claim_rate"] == 0.0
        assert sc["metrics"]["source_coverage_rate"] == 1.0
        assert sc["thresholds"]["incorrect_claim_rate"]["pass"] is True

    def test_all_not_machine_verifiable(self):
        rows = [_row("not_machine_verifiable") for _ in range(3)]
        sc = compute_scorecard(rows)
        assert sc["summary"]["machine_verifiable_claims"] == 0
        assert sc["metrics"]["source_coverage_rate"] == 0.0
        assert sc["metrics"]["incorrect_claim_rate"] == 0.0
        assert sc["thresholds"]["source_coverage_rate"]["pass"] is False

    def test_all_incorrect(self):
        rows = [_row("incorrect") for _ in range(3)]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["incorrect_claim_rate"] == 1.0
        assert sc["thresholds"]["incorrect_claim_rate"]["pass"] is False

    def test_all_unsupported(self):
        rows = [_row("unsupported") for _ in range(5)]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["unsupported_claim_rate"] == 1.0
        assert sc["thresholds"]["unsupported_claim_rate"]["pass"] is False

    def test_single_verified_claim(self):
        sc = compute_scorecard([_row("verified")])
        assert sc["summary"]["total_claims"] == 1
        assert sc["metrics"]["source_coverage_rate"] == 1.0
        assert sc["metrics"]["primary_source_coverage_rate"] == 1.0
        assert sc["metrics"]["incorrect_claim_rate"] == 0.0


# ── Metric formulas ───────────────────────────────────────────────────────────

class TestMetricFormulas:
    def test_scr_formula(self):
        # SCR = machine_verifiable / total = (verified + incorrect) / total
        rows = [
            _row("verified"),
            _row("incorrect"),
            _row("not_machine_verifiable"),
            _row("not_machine_verifiable"),
        ]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["source_coverage_rate"] == pytest.approx(0.5)

    def test_pscr_formula(self):
        # PSCR = verified / machine_verifiable
        rows = [_row("verified"), _row("verified"), _row("incorrect")]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["primary_source_coverage_rate"] == pytest.approx(2 / 3, abs=0.001)

    def test_ucr_formula(self):
        # UCR = unsupported / total
        rows = [_row("unsupported"), _row("verified"), _row("verified"), _row("verified")]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["unsupported_claim_rate"] == pytest.approx(0.25)

    def test_icr_formula(self):
        # ICR = incorrect / machine_verifiable
        rows = [_row("incorrect"), _row("verified"), _row("verified")]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["incorrect_claim_rate"] == pytest.approx(1 / 3, abs=0.001)

    def test_threshold_targets(self):
        sc = compute_scorecard([_row("verified")])
        t = sc["thresholds"]
        assert "source_coverage_rate" in t
        assert "primary_source_coverage_rate" in t
        assert "unsupported_claim_rate" in t
        assert "incorrect_claim_rate" in t
        for name, info in t.items():
            assert "value" in info
            assert "target" in info
            assert "pass" in info
            assert isinstance(info["pass"], bool)


# ── Valuation dispersion ──────────────────────────────────────────────────────

class TestValuationDispersion:
    def test_null_when_fewer_than_two_multiples(self):
        rows = [{"verification_status": "verified", "metric": "pe_ratio",
                 "claimed_value": "37.7x"}]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["valuation_dispersion"] is None

    def test_computed_when_two_multiples(self):
        rows = [
            {"verification_status": "verified", "metric": "pe_ratio", "claimed_value": "30x"},
            {"verification_status": "verified", "metric": "ev_ebitda", "claimed_value": "20x"},
        ]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["valuation_dispersion"] is not None
        assert sc["metrics"]["valuation_dispersion"] >= 0.0

    def test_zero_dispersion_identical_multiples(self):
        rows = [
            {"verification_status": "verified", "metric": "pe_ratio", "claimed_value": "25x"},
            {"verification_status": "verified", "metric": "pe_ratio", "claimed_value": "25x"},
        ]
        sc = compute_scorecard(rows)
        assert sc["metrics"]["valuation_dispersion"] == 0.0


# ── Per-metric breakdown ──────────────────────────────────────────────────────

class TestByMetric:
    def test_by_metric_keys_present(self):
        rows = [
            _row("verified", metric="revenue"),
            _row("incorrect", metric="ebitda_margin"),
        ]
        sc = compute_scorecard(rows)
        assert "revenue" in sc["by_metric"]
        assert "ebitda_margin" in sc["by_metric"]

    def test_by_metric_counts_correct(self):
        rows = [
            _row("verified", metric="revenue"),
            _row("verified", metric="revenue"),
            _row("incorrect", metric="revenue"),
        ]
        sc = compute_scorecard(rows)
        bm = sc["by_metric"]["revenue"]
        assert bm["total"] == 3
        assert bm["verified"] == 2
        assert bm["incorrect"] == 1

    def test_by_metric_handles_source_conflict(self):
        rows = [
            _row("SOURCE_CONFLICT", metric="ebitda"),
            _row("verified", metric="ebitda"),
        ]
        sc = compute_scorecard(rows)
        bm = sc["by_metric"]["ebitda"]
        assert bm["SOURCE_CONFLICT"] == 1
        assert bm["total"] == 2

    def test_by_metric_handles_empty_status(self):
        rows = [_row("", metric="pe_ratio")]
        sc = compute_scorecard(rows)
        assert sc["by_metric"]["pe_ratio"][""] == 1


# ── Sample fixture cross-check ────────────────────────────────────────────────

class TestSampleScorecard:
    """Recompute scorecard from sample_fact_table.csv and compare to sample_scorecard.json."""

    def _load_fact_rows(self):
        import csv
        rows = []
        with open(SAMPLE_FACT_TABLE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def test_recomputed_matches_fixture(self):
        rows = self._load_fact_rows()
        computed = compute_scorecard(rows)
        expected = json.loads(SAMPLE_SCORECARD.read_text())

        # Summary counts
        assert computed["summary"]["total_claims"] == expected["summary"]["total_claims"]
        assert computed["summary"]["verified_count"] == expected["summary"]["verified_count"]
        assert computed["summary"]["incorrect_count"] == expected["summary"]["incorrect_count"]

        # Rates (allow tiny float diff from rounding)
        for key in ("source_coverage_rate", "unsupported_claim_rate", "incorrect_claim_rate"):
            assert abs(computed["metrics"][key] - expected["metrics"][key]) < 0.01, (
                f"{key}: computed={computed['metrics'][key]} expected={expected['metrics'][key]}"
            )

    def test_threshold_pass_fail_matches_fixture(self):
        rows = self._load_fact_rows()
        computed = compute_scorecard(rows)
        expected = json.loads(SAMPLE_SCORECARD.read_text())

        for key in ("source_coverage_rate", "unsupported_claim_rate", "incorrect_claim_rate"):
            assert computed["thresholds"][key]["pass"] == expected["thresholds"][key]["pass"], (
                f"Threshold mismatch on {key}"
            )

    def test_fixture_total_is_five(self):
        rows = self._load_fact_rows()
        assert len(rows) == 5

    def test_fixture_has_one_verified(self):
        rows = self._load_fact_rows()
        sc = compute_scorecard(rows)
        assert sc["summary"]["verified_count"] == 1

    def test_fixture_has_one_incorrect(self):
        rows = self._load_fact_rows()
        sc = compute_scorecard(rows)
        assert sc["summary"]["incorrect_count"] == 1

    def test_fixture_has_three_nmv(self):
        rows = self._load_fact_rows()
        sc = compute_scorecard(rows)
        assert sc["summary"]["not_machine_verifiable"] == 3
