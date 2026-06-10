"""
Tests for PR4 critic modules (quant_risk_reviewer, model_risk_reviewer)
and PR5 investment_committee_memo.

All tests run offline (DEV_MODE=1 enforced by conftest.py).
No LLM calls — tests cover structure, prompting logic, and offline fallback.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.critics.quant_risk_reviewer import (
    run_quant_risk_review,
    _format_scorecard_summary,
    _format_by_metric,
    _compute_source_tier_breakdown,
)
from reliability_lab.critics.model_risk_reviewer import (
    run_model_risk_review,
    _extract_pipeline_metadata,
    _load_run_metadata_entries,
)
from reliability_lab.critics.investment_committee_memo import (
    run_investment_committee_memo,
    _build_locked_facts,
    _build_scorecard_str,
)


# ── Shared fixtures ────────────────────────────────────────────────────────────

def _scorecard(icr=0.05, scr=0.80, vd=0.08):
    return {
        "summary": {"total_claims": 20, "machine_verifiable_claims": 10,
                    "verified_count": 8, "incorrect_count": 1,
                    "unsupported_count": 2, "not_machine_verifiable": 8},
        "metrics": {
            "incorrect_claim_rate":         icr,
            "source_coverage_rate":         scr,
            "primary_source_coverage_rate": 0.90,
            "unsupported_claim_rate":        0.10,
            "valuation_dispersion":          vd,
        },
        "thresholds": {
            "incorrect_claim_rate":         {"value": icr, "target": "≤0.05", "pass": icr <= 0.05},
            "source_coverage_rate":         {"value": scr, "target": "≥0.80", "pass": scr >= 0.80},
            "primary_source_coverage_rate": {"value": 0.90, "target": "≥0.90", "pass": True},
            "unsupported_claim_rate":       {"value": 0.10, "target": "≤0.15", "pass": True},
        },
        "by_metric": {
            "revenue":  {"total": 3, "verified": 2, "incorrect": 1, "unsupported": 0, "not_machine_verifiable": 0},
            "pe_ratio": {"total": 2, "verified": 1, "incorrect": 0, "unsupported": 1, "not_machine_verifiable": 0},
        },
    }


def _fact_rows():
    return [
        {"metric": "revenue", "period": "2023", "claimed_value": "$27B",
         "verified_value": "$26.97B", "source": "SEC EDGAR 10-K",
         "source_tier": "1", "verification_status": "verified", "notes": ""},
        {"metric": "pe_ratio", "period": "2023", "claimed_value": "37.7x",
         "verified_value": "36.2x", "source": "FMP ratios FY2023",
         "source_tier": "3", "verification_status": "verified", "notes": ""},
        {"metric": "revenue", "period": "2024", "claimed_value": "$60.9B",
         "verified_value": "", "source": "",
         "source_tier": "", "verification_status": "not_machine_verifiable", "notes": ""},
    ]


# ── Quant Risk Reviewer ────────────────────────────────────────────────────────

class TestQuantRiskReviewerHelpers:
    def test_format_scorecard_summary_has_key_fields(self):
        s = _format_scorecard_summary(_scorecard())
        assert "Total claims" in s
        assert "Incorrect claim rate" in s
        assert "Source coverage rate" in s

    def test_format_by_metric_has_metric_name(self):
        s = _format_by_metric(_scorecard())
        assert "revenue" in s
        assert "pe_ratio" in s

    def test_format_by_metric_empty_scorecard(self):
        s = _format_by_metric({"by_metric": {}})
        assert "no per-metric breakdown" in s

    def test_source_tier_breakdown_counts_correctly(self):
        rows = [
            {"source_tier": "1", "verification_status": "verified"},
            {"source_tier": "1", "verification_status": "incorrect"},
            {"source_tier": "3", "verification_status": "verified"},
            {"source_tier": "", "verification_status": "not_machine_verifiable"},
        ]
        tb = _compute_source_tier_breakdown(rows)
        assert tb["tier_1_fraction"] == pytest.approx(2/3, abs=0.01)
        assert tb["tier_3_fraction"] == pytest.approx(1/3, abs=0.01)

    def test_source_tier_breakdown_empty_rows(self):
        tb = _compute_source_tier_breakdown([])
        assert tb["tier_1_fraction"] == 0.0
        assert tb["tier_3_fraction"] == 0.0


class TestQuantRiskReviewOffline:
    def test_no_crash_with_fact_rows(self, tmp_path):
        # Ollama fallback may respond; accept None or a valid dict
        result = run_quant_risk_review("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        assert result is None or isinstance(result, dict)
        if result:
            assert result["ticker"] == "NVDA"

    def test_no_crash_with_empty_fact_rows(self, tmp_path):
        result = run_quant_risk_review("NVDA", _scorecard(), [], str(tmp_path))
        assert result is None or isinstance(result, dict)


# ── Model Risk Reviewer ────────────────────────────────────────────────────────

class TestModelRiskReviewerHelpers:
    def test_extract_pipeline_metadata_defaults(self):
        pm = _extract_pipeline_metadata([], _scorecard())
        assert pm["extractor_model"] == "unknown"
        assert pm["extractor_provider"] == "unknown"
        assert pm["fallback_used"] is False
        assert pm["total_claims"] == 20

    def test_extract_pipeline_metadata_from_entries(self):
        entries = [
            {"phase": "claim_extraction", "model_name": "claude-sonnet-4-6",
             "provider": "anthropic", "prompt_version": "claim_extractor_v1",
             "fallback_used": False},
            {"phase": "skeptical_analyst", "model_name": "claude-sonnet-4-6",
             "provider": "anthropic", "prompt_version": "skeptical_analyst_v1",
             "fallback_used": False},
        ]
        pm = _extract_pipeline_metadata(entries, _scorecard())
        assert pm["extractor_model"] == "claude-sonnet-4-6"
        assert pm["extractor_provider"] == "anthropic"
        assert pm["claim_prompt_version"] == "claim_extractor_v1"
        assert pm["critic_model"] == "claude-sonnet-4-6"

    def test_load_run_metadata_entries_missing_file(self, tmp_path):
        entries = _load_run_metadata_entries(str(tmp_path), "NVDA")
        assert entries == []

    def test_load_run_metadata_entries_valid_file(self, tmp_path):
        path = tmp_path / "NVDA_run_metadata.jsonl"
        path.write_text('{"phase": "claim_extraction", "model_name": "test"}\n')
        entries = _load_run_metadata_entries(str(tmp_path), "NVDA")
        assert len(entries) == 1
        assert entries[0]["phase"] == "claim_extraction"


class TestModelRiskReviewOffline:
    def test_no_crash_returns_dict_or_none(self, tmp_path):
        result = run_model_risk_review("NVDA", _scorecard(), str(tmp_path))
        assert result is None or isinstance(result, dict)
        if result:
            assert result["ticker"] == "NVDA"

    def test_no_crash_with_missing_run_metadata(self, tmp_path):
        result = run_model_risk_review("TSLA", _scorecard(), str(tmp_path))
        assert result is None or isinstance(result, dict)


# ── Investment Committee Memo ──────────────────────────────────────────────────

class TestICMemoHelpers:
    def test_build_locked_facts_only_verified(self):
        rows = _fact_rows()
        locked = _build_locked_facts(rows)
        assert "SEC EDGAR 10-K" in locked
        # Not-machine-verifiable should not appear
        assert "not_machine_verifiable" not in locked

    def test_build_locked_facts_empty(self):
        result = _build_locked_facts([])
        assert "no verified claims" in result

    def test_build_locked_facts_no_verified_rows(self):
        rows = [{"verification_status": "unsupported", "metric": "revenue",
                 "period": "2023", "claimed_value": "", "verified_value": "",
                 "source": "", "source_tier": ""}]
        result = _build_locked_facts(rows)
        assert "no verified claims" in result

    def test_build_scorecard_str_has_key_fields(self):
        s = _build_scorecard_str(_scorecard())
        assert "Source coverage rate" in s
        assert "Incorrect claim rate" in s
        assert "Gate decision" in s

    def test_build_scorecard_str_with_gate(self):
        gate = {"decision": "HUMAN_REVIEW"}
        s = _build_scorecard_str(_scorecard(), gate=gate)
        assert "HUMAN_REVIEW" in s


class TestICMemoOffline:
    def test_no_crash_returns_str_or_none(self, tmp_path):
        memo = run_investment_committee_memo(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path)
        )
        assert memo is None or isinstance(memo, str)
        if memo:
            assert "NVDA" in memo

    def test_no_crash_with_missing_recommendation_file(self, tmp_path):
        memo = run_investment_committee_memo(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path)
        )
        assert memo is None or isinstance(memo, str)


# ── Schema validation for new schemas ─────────────────────────────────────────

try:
    from jsonschema.validators import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMAS = Path(__file__).parent.parent / "schemas"


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestNewSchemas:
    def _validate(self, instance, schema_name):
        schema = json.loads((SCHEMAS / schema_name).read_text())
        Draft202012Validator(schema).validate(instance)

    def test_quant_risk_review_minimal_valid(self):
        obj = {
            "ticker": "NVDA",
            "icr_assessment": "ICR of 0.05 is at the target threshold.",
            "quant_risk_verdict": "medium",
            "quant_risk_rationale": "Coverage is acceptable but valuation dispersion is elevated.",
        }
        self._validate(obj, "quant_risk_review.schema.json")

    def test_quant_risk_review_full_valid(self):
        obj = {
            "ticker": "NVDA",
            "icr_assessment": "Low ICR, primarily period-attribution artifact.",
            "coverage_gaps": ["ebitda", "free_cash_flow"],
            "valuation_dispersion_assessment": "VD=0.08 is within tolerance.",
            "source_tier_breakdown": {"tier_1_fraction": 0.7, "tier_3_fraction": 0.3},
            "quant_risk_verdict": "low",
            "quant_risk_rationale": "Strong Tier 1 coverage and low ICR.",
        }
        self._validate(obj, "quant_risk_review.schema.json")

    def test_quant_risk_review_invalid_verdict(self):
        obj = {
            "ticker": "NVDA",
            "icr_assessment": "ok",
            "quant_risk_verdict": "extreme",  # not in enum
            "quant_risk_rationale": "test",
        }
        with pytest.raises(Exception):
            self._validate(obj, "quant_risk_review.schema.json")

    def test_model_risk_review_minimal_valid(self):
        obj = {
            "ticker": "NVDA",
            "determinism_risk": "low",
            "input_sensitivity_risk": "medium",
            "coverage_gap_risk": "medium",
            "prompt_fragility": "medium",
            "model_risk_verdict": "prototype",
        }
        self._validate(obj, "model_risk_review.schema.json")

    def test_model_risk_review_full_valid(self):
        obj = {
            "ticker": "TSLA",
            "determinism_risk": "medium",
            "determinism_notes": "Ollama fallback used; hardware-dependent outputs.",
            "input_sensitivity_risk": "high",
            "input_sensitivity_notes": "120-char window misses table-embedded figures.",
            "coverage_gap_risk": "high",
            "coverage_gap_notes": "SCR=0.20 — 80% of claims unverifiable.",
            "prompt_fragility": "medium",
            "model_risk_verdict": "conditional-production",
            "conditions_for_upgrade": ["SCR ≥ 0.80", "ICR ≤ 0.05 on 3 consecutive runs"],
        }
        self._validate(obj, "model_risk_review.schema.json")

    def test_model_risk_review_invalid_verdict(self):
        obj = {
            "ticker": "NVDA",
            "determinism_risk": "low",
            "input_sensitivity_risk": "low",
            "coverage_gap_risk": "low",
            "prompt_fragility": "low",
            "model_risk_verdict": "ready",  # not in enum
        }
        with pytest.raises(Exception):
            self._validate(obj, "model_risk_review.schema.json")
