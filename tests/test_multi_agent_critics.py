"""
Tests for G2 multi-agent critic modules.
All tests run offline — LLM calls are patched out.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.critics.earnings_analyst import run_earnings_analysis
from reliability_lab.critics.valuation_agent import run_valuation_analysis
from reliability_lab.critics.coherence_agent import run_coherence_analysis
from reliability_lab.critics.multi_agent_synthesizer import run_multi_agent_review, _aggregate_verdicts

_LLM = "reliability_lab.critic_agents._llm_call"
_LOAD_PROMPT = "reliability_lab.claim_extraction._load_prompt"

_SAMPLE_FACT_ROWS = [
    {"ticker": "NVDA", "metric": "revenue", "period": "2023",
     "claimed_value": "$27B", "verified_value": "$26.97B",
     "source": "SEC EDGAR", "source_tier": "1",
     "verification_status": "verified", "notes": ""},
    {"ticker": "NVDA", "metric": "eps", "period": "2023",
     "claimed_value": "$6.50", "verified_value": "$6.50",
     "source": "FMP ratios", "source_tier": "3",
     "verification_status": "verified", "notes": ""},
    {"ticker": "NVDA", "metric": "pe_ratio", "period": "2023",
     "claimed_value": "$39.9", "verified_value": "25.0x",
     "source": "FMP ratios", "source_tier": "3",
     "verification_status": "incorrect", "notes": ""},
    {"ticker": "NVDA", "metric": "revenue_growth", "period": "2023",
     "claimed_value": "122%", "verified_value": "122.4%",
     "source": "SEC EDGAR", "source_tier": "1",
     "verification_status": "verified", "notes": ""},
    {"ticker": "NVDA", "metric": "guidance_forward", "period": "2025",
     "claimed_value": "$200B", "verified_value": "",
     "source": "forward-looking", "source_tier": "",
     "verification_status": "not_machine_verifiable", "notes": ""},
]

_SAMPLE_SCORECARD = {
    "metrics": {
        "source_coverage_rate": 0.30,
        "primary_source_coverage_rate": 0.20,
        "incorrect_claim_rate": 0.10,
        "unsupported_claim_rate": 0.05,
        "valuation_dispersion": 0.45,
    },
    "summary": {
        "total_claims": 30,
        "machine_verifiable_claims": 9,
        "verified_count": 8,
        "incorrect_count": 3,
    },
    "thresholds": {},
    "by_metric": {},
}


# ── Earnings Analyst ───────────────────────────────────────────────────────────

class TestEarningsAnalyst:
    def test_returns_dict_on_success(self, tmp_path):
        mock_response = json.dumps({
            "revenue_accuracy": "Within 0.1% of SEC EDGAR — accurate.",
            "eps_accuracy": "Within tolerance.",
            "margin_consistency": "Consistent.",
            "forward_projection_flags": ["$200B FY2025 stated without qualification"],
            "key_discrepancies": ["pe_ratio: claimed $39.9 vs 25.0x"],
            "earnings_quality_verdict": "medium",
            "earnings_quality_rationale": "Revenue accurate, one forward projection issue.",
        })
        with patch(_LLM, return_value=(mock_response, "anthropic", "claude-test")), \
             patch(_LOAD_PROMPT, return_value="template {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert result["earnings_quality_verdict"] == "medium"
        assert "_computed" in result
        assert result["_computed"]["earnings_verified"] >= 1

    def test_skips_non_earnings_metrics(self, tmp_path):
        rows = [{"metric": "peer_comparison", "period": "2023",
                 "claimed_value": "x", "verified_value": "",
                 "verification_status": "not_machine_verifiable"}]
        with patch(_LLM, return_value=('{"earnings_quality_verdict":"low","earnings_quality_rationale":"test"}',
                                        "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result["_computed"]["earnings_claims_total"] == 0

    def test_returns_none_when_no_llm(self, tmp_path):
        with patch(_LLM, return_value=("", "", "")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_returns_none_when_prompt_missing(self, tmp_path):
        with patch(_LOAD_PROMPT, side_effect=FileNotFoundError("missing")):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_handles_malformed_json(self, tmp_path):
        with patch(_LLM, return_value=("not json", "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert "earnings_quality_verdict" in result

    def test_writes_output_file(self, tmp_path):
        mock_json = '{"earnings_quality_verdict":"high","earnings_quality_rationale":"great"}'
        with patch(_LLM, return_value=(mock_json, "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert (tmp_path / "NVDA_earnings_analysis.json").exists()

    def test_computed_icr_correct(self, tmp_path):
        rows = [
            {"metric": "revenue", "period": "2023", "claimed_value": "$27B",
             "verified_value": "$27B", "verification_status": "verified"},
            {"metric": "eps", "period": "2023", "claimed_value": "$6",
             "verified_value": "$10", "verification_status": "incorrect"},
        ]
        with patch(_LLM, return_value=('{"earnings_quality_verdict":"low","earnings_quality_rationale":"x"}',
                                        "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result["_computed"]["earnings_icr"] == 0.5
        assert result["_computed"]["earnings_verified"] == 1
        assert result["_computed"]["earnings_incorrect"] == 1


# ── Valuation Agent ────────────────────────────────────────────────────────────

class TestValuationAgent:

    def test_returns_dict_on_success(self, tmp_path):
        mock_response = json.dumps({
            "multiple_reasonableness": "P/E of 25x is normal for semiconductors.",
            "internal_consistency": "Consistent.",
            "peer_comparison_flags": [],
            "price_target_assessment": "no price target stated",
            "valuation_dispersion_interpretation": "VD=0.45 is high.",
            "valuation_verdict": "questionable",
            "valuation_rationale": "High VD despite reasonable individual multiples.",
        })
        with patch(_LLM, return_value=(mock_response, "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert result["valuation_verdict"] == "questionable"
        assert result["_computed"]["sector"] == "Technology"

    def test_infers_sector(self, tmp_path):
        with patch(_LLM, return_value=('{"valuation_verdict":"sound","valuation_rationale":"ok"}',
                                        "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("JPM", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result["_computed"]["sector"] == "Finance"

    def test_returns_none_on_no_llm(self, tmp_path):
        with patch(_LLM, return_value=("", "", "")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_writes_output_file(self, tmp_path):
        with patch(_LLM, return_value=('{"valuation_verdict":"sound","valuation_rationale":"x"}',
                                        "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            run_valuation_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert (tmp_path / "NVDA_valuation_analysis.json").exists()


# ── Coherence Agent ────────────────────────────────────────────────────────────

class TestCoherenceAgent:

    def test_returns_dict_on_success(self, tmp_path):
        mock_response = json.dumps({
            "recommendation_quality_alignment": "BUY with ICR 0.10 is borderline.",
            "thesis_consistency": "Revenue accurate; P/E overstatement is a concern.",
            "confidence_calibration": "Report lacks uncertainty qualifiers on forward projections.",
            "coherence_flags": ["P/E overstated by 60%"],
            "signal_reliability": "conditional",
            "coherence_rationale": "Some concerns but not disqualifying.",
            "final_disposition": "Use with analyst review of P/E and forward projection claims.",
        })
        gate = {"decision": "HUMAN_REVIEW"}
        with patch(_LLM, return_value=(mock_response, "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {recommendation} {icr} {scr} "
                                              "{gate_decision} {scorecard_summary} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_coherence_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS,
                                                  str(tmp_path), gate)
        assert result is not None
        assert result["signal_reliability"] == "conditional"
        assert result["_computed"]["gate_decision"] == "HUMAN_REVIEW"

    def test_reads_existing_critic_files(self, tmp_path):
        (tmp_path / "NVDA_quant_risk_review.json").write_text(
            json.dumps({"quant_risk_verdict": "high"})
        )
        (tmp_path / "NVDA_earnings_analysis.json").write_text(
            json.dumps({"earnings_quality_verdict": "low"})
        )
        with patch(_LLM, return_value=('{"signal_reliability":"unreliable","coherence_rationale":"x",'
                                        '"coherence_flags":[],"final_disposition":"no"}',
                                        "anthropic", "test")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {recommendation} {icr} {scr} "
                                              "{gate_decision} {scorecard_summary} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_coherence_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS,
                                                  str(tmp_path))
        assert result["_computed"]["specialist_verdicts"]["quant_risk_verdict"] == "high"
        assert result["_computed"]["specialist_verdicts"]["earnings_quality_verdict"] == "low"

    def test_returns_none_on_no_llm(self, tmp_path):
        with patch(_LLM, return_value=("", "", "")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {recommendation} {icr} {scr} "
                                              "{gate_decision} {scorecard_summary} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_coherence_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS,
                                                  str(tmp_path))
        assert result is None


# ── Multi-Agent Synthesizer ────────────────────────────────────────────────────

class TestMultiAgentSynthesizer:

    def test_aggregate_all_good(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "high"},
            {"valuation_verdict": "sound"},
            {"signal_reliability": "reliable"},
        )
        assert result["panel_verdict"] == "CONCERN"  # "high" earnings = concern

    def test_aggregate_all_medium(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "medium"},
            {"valuation_verdict": "questionable"},
            {"signal_reliability": "conditional"},
        )
        assert result["panel_verdict"] == "REVIEW"

    def test_aggregate_all_good_low(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "low"},
            {"valuation_verdict": "sound"},
            {"signal_reliability": "reliable"},
        )
        assert result["panel_verdict"] == "ACCEPTABLE"

    def test_aggregate_none_agents(self):
        result = _aggregate_verdicts(None, None, None)
        assert result["panel_verdict"] == "ACCEPTABLE"
        assert result["specialist_verdicts"] == {}

    def test_full_review_runs(self, tmp_path):
        mock_resp = '{"earnings_quality_verdict":"medium","earnings_quality_rationale":"ok"}'
        mock_val = '{"valuation_verdict":"sound","valuation_rationale":"ok"}'
        mock_coh = ('{"signal_reliability":"conditional","coherence_rationale":"ok",'
                    '"coherence_flags":[],"final_disposition":"review"}')
        with patch(_LLM, side_effect=[
            (mock_resp, "anthropic", "test"),
            (mock_val, "anthropic", "test"),
            (mock_coh, "anthropic", "test"),
        ]), patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary} "
                                             "{sector} {valuation_rows} {valuation_dispersion} "
                                             "{recommendation} {icr} {scr} {gate_decision} "
                                             "{quant_risk_verdict} {model_risk_verdict} "
                                             "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_multi_agent_review("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result["ticker"] == "NVDA"
        assert len(result["agents_run"]) == 3
        assert (tmp_path / "NVDA_multi_agent_review.json").exists()

    def test_skips_agents_on_no_llm(self, tmp_path):
        with patch(_LLM, return_value=("", "", "")), \
             patch(_LOAD_PROMPT, return_value="x {ticker} {earnings_rows} {scorecard_summary} "
                                              "{sector} {valuation_rows} {valuation_dispersion} "
                                              "{recommendation} {icr} {scr} {gate_decision} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_multi_agent_review("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result["agents_run"] == []
        assert len(result["agents_skipped"]) == 3
        assert result["panel_verdict"] == "ACCEPTABLE"
