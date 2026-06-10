"""
Tests for reliability_lab/scoring/gates.py.

Covers PASS / HUMAN_REVIEW / FAIL decision logic and output structure.
No live API calls.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.scoring.gates import evaluate_gate, save_gate_decision


# ── Helpers ────────────────────────────────────────────────────────────────────

def _scorecard(icr=0.0, scr=1.0, pscr=1.0, ucr=0.0, vd=None):
    """Build a minimal scorecard dict with the given metric values."""
    icr_pass   = icr  <= 0.05
    scr_pass   = scr  >= 0.80
    pscr_pass  = pscr >= 0.90
    ucr_pass   = ucr  <= 0.15
    return {
        "summary": {"total_claims": 10, "machine_verifiable_claims": 8,
                    "verified_count": 7, "incorrect_count": 1,
                    "unsupported_count": 1, "not_machine_verifiable": 1},
        "metrics": {
            "incorrect_claim_rate":         icr,
            "source_coverage_rate":         scr,
            "primary_source_coverage_rate": pscr,
            "unsupported_claim_rate":       ucr,
            "valuation_dispersion":         vd,
        },
        "thresholds": {
            "incorrect_claim_rate":         {"value": icr,  "target": "≤0.05",  "pass": icr_pass},
            "source_coverage_rate":         {"value": scr,  "target": "≥0.80",  "pass": scr_pass},
            "primary_source_coverage_rate": {"value": pscr, "target": "≥0.90",  "pass": pscr_pass},
            "unsupported_claim_rate":       {"value": ucr,  "target": "≤0.15",  "pass": ucr_pass},
        },
        "by_metric": {},
    }


def _conflict_rows(n=1, total=10):
    """Generate fact rows with n SOURCE_CONFLICT entries."""
    rows = [{"verification_status": "SOURCE_CONFLICT"} for _ in range(n)]
    rows += [{"verification_status": "verified"} for _ in range(total - n)]
    return rows


# ── PASS decision ──────────────────────────────────────────────────────────────

class TestPassDecision:
    def test_all_thresholds_pass_gives_pass(self):
        sc = _scorecard(icr=0.02, scr=0.85, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "PASS"

    def test_pass_has_no_hard_failures(self):
        gate = evaluate_gate(_scorecard(), "NVDA")
        assert gate["hard_failures"] == []

    def test_pass_has_no_hr_triggers(self):
        gate = evaluate_gate(_scorecard(), "NVDA")
        assert gate["human_review_triggers"] == []

    def test_pass_with_zero_vd(self):
        sc = _scorecard(icr=0.02, scr=0.90, pscr=1.0, ucr=0.05, vd=0.05)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "PASS"


# ── HUMAN_REVIEW decision ──────────────────────────────────────────────────────

class TestHumanReviewDecision:
    def test_icr_above_target_gives_human_review(self):
        sc = _scorecard(icr=0.08, scr=0.85, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "HUMAN_REVIEW"

    def test_scr_below_target_gives_human_review(self):
        sc = _scorecard(icr=0.02, scr=0.70, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "HUMAN_REVIEW"

    def test_high_vd_gives_human_review(self):
        sc = _scorecard(icr=0.02, scr=0.85, pscr=0.95, ucr=0.10, vd=0.15)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "HUMAN_REVIEW"

    def test_source_conflict_gives_human_review(self):
        sc = _scorecard(icr=0.02, scr=0.85, pscr=0.95, ucr=0.10)
        rows = _conflict_rows(n=1, total=10)
        gate = evaluate_gate(sc, "NVDA", fact_rows=rows)
        assert gate["decision"] == "HUMAN_REVIEW"
        assert "unresolved_source_conflict" in gate["human_review_triggers"]

    def test_ucr_above_target_gives_human_review(self):
        sc = _scorecard(icr=0.02, scr=0.85, pscr=0.95, ucr=0.20)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "HUMAN_REVIEW"


# ── FAIL decision ──────────────────────────────────────────────────────────────

class TestFailDecision:
    def test_icr_above_fail_threshold_gives_fail(self):
        sc = _scorecard(icr=0.20, scr=0.85, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "FAIL"

    def test_scr_below_fail_threshold_gives_fail(self):
        sc = _scorecard(icr=0.02, scr=0.05, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "FAIL"

    def test_high_conflict_ratio_gives_fail(self):
        sc = _scorecard(icr=0.02, scr=0.85, pscr=0.95, ucr=0.10)
        # 3 conflicts out of 10 = 30% > 20% threshold
        rows = _conflict_rows(n=3, total=10)
        gate = evaluate_gate(sc, "NVDA", fact_rows=rows)
        assert gate["decision"] == "FAIL"

    def test_fail_hard_failures_not_empty(self):
        sc = _scorecard(icr=0.20, scr=0.85, pscr=0.95, ucr=0.10)
        gate = evaluate_gate(sc, "NVDA")
        assert len(gate["hard_failures"]) > 0

    def test_fail_overrides_human_review(self):
        # Even if some thresholds merely trigger HUMAN_REVIEW, ICR at FAIL level → FAIL
        sc = _scorecard(icr=0.20, scr=0.70, pscr=0.80, ucr=0.20)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "FAIL"


# ── Output structure ───────────────────────────────────────────────────────────

class TestGateOutputStructure:
    def test_required_fields_present(self):
        gate = evaluate_gate(_scorecard(), "NVDA")
        for field in ("ticker", "decision", "scorecard_ref", "reasons",
                      "hard_failures", "human_review_triggers", "timestamp"):
            assert field in gate, f"Missing field: {field}"

    def test_ticker_preserved(self):
        gate = evaluate_gate(_scorecard(), "TSLA")
        assert gate["ticker"] == "TSLA"

    def test_run_id_passed_through(self):
        gate = evaluate_gate(_scorecard(), "NVDA", run_id="test-run-1")
        assert gate["run_id"] == "test-run-1"

    def test_scorecard_ref_passed_through(self):
        gate = evaluate_gate(_scorecard(), "NVDA", scorecard_ref="output/NVDA/scorecard.json")
        assert gate["scorecard_ref"] == "output/NVDA/scorecard.json"

    def test_reasons_list_not_empty(self):
        gate = evaluate_gate(_scorecard(), "NVDA")
        assert isinstance(gate["reasons"], list)
        assert len(gate["reasons"]) > 0

    def test_each_reason_has_required_fields(self):
        gate = evaluate_gate(_scorecard(), "NVDA")
        for r in gate["reasons"]:
            for f in ("metric", "value", "threshold", "status"):
                assert f in r, f"Reason missing field {f}: {r}"

    def test_timestamp_is_iso_format(self):
        from datetime import datetime
        gate = evaluate_gate(_scorecard(), "NVDA")
        ts = gate["timestamp"]
        # Should parse as ISO datetime without raising
        datetime.fromisoformat(ts)

    def test_save_gate_decision_writes_json(self, tmp_path):
        gate = evaluate_gate(_scorecard(), "NVDA")
        path = save_gate_decision(gate, str(tmp_path), "NVDA")
        assert path.exists()
        import json
        loaded = json.loads(path.read_text())
        assert loaded["ticker"] == "NVDA"
        assert loaded["decision"] in ("PASS", "HUMAN_REVIEW", "FAIL")


# ── Edge cases ─────────────────────────────────────────────────────────────────

class TestGateEdgeCases:
    def test_empty_fact_rows_no_crash(self):
        gate = evaluate_gate(_scorecard(), "NVDA", fact_rows=[])
        assert gate["decision"] in ("PASS", "HUMAN_REVIEW", "FAIL")

    def test_none_fact_rows_no_crash(self):
        gate = evaluate_gate(_scorecard(), "NVDA", fact_rows=None)
        assert gate["decision"] in ("PASS", "HUMAN_REVIEW", "FAIL")

    def test_vd_none_no_crash(self):
        sc = _scorecard(vd=None)
        gate = evaluate_gate(sc, "NVDA")
        assert gate["decision"] == "PASS"

    def test_zero_total_claims_no_crash(self):
        sc = _scorecard()
        sc["summary"]["total_claims"] = 0
        gate = evaluate_gate(sc, "NVDA", fact_rows=[])
        assert gate["decision"] in ("PASS", "HUMAN_REVIEW", "FAIL")
