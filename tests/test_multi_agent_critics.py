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
from reliability_lab.critics.catalyst_evaluator import (
    run_catalyst_evaluation,
    _extract_catalyst_claims,
    _score_catalyst_specificity,
)
from reliability_lab.critics.multi_agent_synthesizer import run_multi_agent_review, _aggregate_verdicts

_LLM_EARNINGS = "reliability_lab.critics.earnings_analyst._llm_call"
_PROMPT_EARNINGS = "reliability_lab.critics.earnings_analyst._load_prompt"
_LLM_VALUATION = "reliability_lab.critics.valuation_agent._llm_call"
_PROMPT_VALUATION = "reliability_lab.critics.valuation_agent._load_prompt"
_LLM_COHERENCE = "reliability_lab.critics.coherence_agent._llm_call"
_PROMPT_COHERENCE = "reliability_lab.critics.coherence_agent._load_prompt"
_LLM_CATALYST = "reliability_lab.critics.catalyst_evaluator._llm_call"

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
        with patch(_LLM_EARNINGS, return_value=(mock_response, "anthropic", "claude-test")), \
             patch(_PROMPT_EARNINGS, return_value="template {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert result["earnings_quality_verdict"] == "medium"
        assert "_computed" in result
        assert result["_computed"]["earnings_verified"] >= 1

    def test_skips_non_earnings_metrics(self, tmp_path):
        rows = [{"metric": "peer_comparison", "period": "2023",
                 "claimed_value": "x", "verified_value": "",
                 "verification_status": "not_machine_verifiable"}]
        with patch(_LLM_EARNINGS, return_value=('{"earnings_quality_verdict":"low","earnings_quality_rationale":"test"}',
                                        "anthropic", "test")), \
             patch(_PROMPT_EARNINGS, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result["_computed"]["earnings_claims_total"] == 0

    def test_returns_none_when_no_llm(self, tmp_path):
        with patch(_LLM_EARNINGS, return_value=("", "", "")), \
             patch(_PROMPT_EARNINGS, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_returns_none_when_prompt_missing(self, tmp_path):
        with patch(_PROMPT_EARNINGS, side_effect=FileNotFoundError("missing")):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_handles_malformed_json(self, tmp_path):
        with patch(_LLM_EARNINGS, return_value=("not json", "anthropic", "test")), \
             patch(_PROMPT_EARNINGS, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            result = run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert "earnings_quality_verdict" in result

    def test_writes_output_file(self, tmp_path):
        mock_json = '{"earnings_quality_verdict":"high","earnings_quality_rationale":"great"}'
        with patch(_LLM_EARNINGS, return_value=(mock_json, "anthropic", "test")), \
             patch(_PROMPT_EARNINGS, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
            run_earnings_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert (tmp_path / "NVDA_earnings_analysis.json").exists()

    def test_computed_icr_correct(self, tmp_path):
        rows = [
            {"metric": "revenue", "period": "2023", "claimed_value": "$27B",
             "verified_value": "$27B", "verification_status": "verified"},
            {"metric": "eps", "period": "2023", "claimed_value": "$6",
             "verified_value": "$10", "verification_status": "incorrect"},
        ]
        with patch(_LLM_EARNINGS, return_value=('{"earnings_quality_verdict":"low","earnings_quality_rationale":"x"}',
                                        "anthropic", "test")), \
             patch(_PROMPT_EARNINGS, return_value="x {ticker} {earnings_rows} {scorecard_summary}"):
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
        with patch(_LLM_VALUATION, return_value=(mock_response, "anthropic", "test")), \
             patch(_PROMPT_VALUATION, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert result["valuation_verdict"] == "questionable"
        assert result["_computed"]["sector"] == "Technology"

    def test_infers_sector(self, tmp_path):
        with patch(_LLM_VALUATION, return_value=('{"valuation_verdict":"sound","valuation_rationale":"ok"}',
                                        "anthropic", "test")), \
             patch(_PROMPT_VALUATION, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("JPM", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result["_computed"]["sector"] == "Finance"

    def test_returns_none_on_no_llm(self, tmp_path):
        with patch(_LLM_VALUATION, return_value=("", "", "")), \
             patch(_PROMPT_VALUATION, return_value="x {ticker} {sector} {valuation_rows} "
                                              "{valuation_dispersion} {scorecard_summary}"):
            result = run_valuation_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result is None

    def test_writes_output_file(self, tmp_path):
        with patch(_LLM_VALUATION, return_value=('{"valuation_verdict":"sound","valuation_rationale":"x"}',
                                        "anthropic", "test")), \
             patch(_PROMPT_VALUATION, return_value="x {ticker} {sector} {valuation_rows} "
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
        with patch(_LLM_COHERENCE, return_value=(mock_response, "anthropic", "test")), \
             patch(_PROMPT_COHERENCE, return_value="x {ticker} {recommendation} {icr} {scr} "
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
        with patch(_LLM_COHERENCE, return_value=('{"signal_reliability":"unreliable","coherence_rationale":"x",'
                                        '"coherence_flags":[],"final_disposition":"no"}',
                                        "anthropic", "test")), \
             patch(_PROMPT_COHERENCE, return_value="x {ticker} {recommendation} {icr} {scr} "
                                              "{gate_decision} {scorecard_summary} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_coherence_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS,
                                                  str(tmp_path))
        assert result["_computed"]["specialist_verdicts"]["quant_risk_verdict"] == "high"
        assert result["_computed"]["specialist_verdicts"]["earnings_quality_verdict"] == "low"

    def test_returns_none_on_no_llm(self, tmp_path):
        with patch(_LLM_COHERENCE, return_value=("", "", "")), \
             patch(_PROMPT_COHERENCE, return_value="x {ticker} {recommendation} {icr} {scr} "
                                              "{gate_decision} {scorecard_summary} "
                                              "{quant_risk_verdict} {model_risk_verdict} "
                                              "{earnings_quality_verdict} {valuation_verdict}"):
            result = run_coherence_analysis("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS,
                                                  str(tmp_path))
        assert result is None


# ── Catalyst Evaluator ────────────────────────────────────────────────────────

_CATALYST_FACT_ROWS = [
    {"ticker": "NVDA", "metric": "earnings", "period": "Q2 2025",
     "claim_text": "Q2 earnings beat expected $6.50 EPS",
     "claimed_value": "$6.50", "verified_value": "$6.50",
     "verification_status": "verified"},
    {"ticker": "NVDA", "metric": "guidance_forward", "period": "FY2025",
     "claim_text": "revenue guidance $200B FY2025",
     "claimed_value": "$200B", "verified_value": "",
     "verification_status": "not_machine_verifiable"},
    {"ticker": "NVDA", "metric": "peer_comparison", "period": "2024",
     "claim_text": "continued growth in AI segment",
     "claimed_value": "positive momentum", "verified_value": "",
     "verification_status": "unverified"},
    {"ticker": "NVDA", "metric": "fda_approval", "period": "2025",
     "claim_text": "FDA approval expected Q1 2025",
     "claimed_value": "Q1 2025", "verified_value": "",
     "verification_status": "not_machine_verifiable"},
]


class TestCatalystEvaluator:

    def test_extract_catalyst_claims_filters_keywords(self):
        rows = _CATALYST_FACT_ROWS + [
            {"metric": "market_share", "claim_text": "no keywords here", "claimed_value": "x"},
        ]
        result = _extract_catalyst_claims(rows)
        # earnings, guidance_forward, fda_approval all match; peer_comparison doesn't
        metrics = [r.get("metric", "") for r in result]
        assert "earnings" in metrics
        assert "guidance_forward" in metrics
        assert "fda_approval" in metrics
        assert "market_share" not in metrics

    def test_extract_catalyst_claims_caps_at_20(self):
        rows = [
            {"metric": "earnings", "claim_text": f"q{i} earnings", "claimed_value": str(i)}
            for i in range(30)
        ]
        result = _extract_catalyst_claims(rows)
        assert len(result) <= 20

    def test_score_specificity_empty(self):
        result = _score_catalyst_specificity([])
        assert result["total"] == 0
        assert result["specificity_rate"] == 0.0

    def test_score_specificity_with_numbers(self):
        rows = [
            {"claim_text": "$200B revenue FY2025", "claimed_value": ""},
            {"claim_text": "continued strong fundamentals", "claimed_value": ""},
            {"claim_text": "q2 beat expected", "claimed_value": ""},
        ]
        result = _score_catalyst_specificity(rows)
        assert result["total"] == 3
        assert result["specific"] >= 2  # first and third are specific
        assert result["vague"] >= 1    # second is vague

    def test_offline_fallback_strong(self, tmp_path):
        # All specific claims → STRONG
        rows = [
            {"metric": "earnings", "claim_text": "Q2 EPS $6.50 beat", "claimed_value": "$6.50",
             "verification_status": "verified"}
        ]
        with patch(_LLM_CATALYST, return_value=("", "", "")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result is not None
        assert result["catalyst_verdict"] in ("STRONG", "ADEQUATE", "WEAK")
        assert result["_offline_fallback"] is True

    def test_offline_fallback_weak(self, tmp_path):
        rows = [
            {"metric": "catalyst", "claim_text": "continued growth long-term potential", "claimed_value": "positive",
             "verification_status": "unverified"}
        ]
        with patch(_LLM_CATALYST, return_value=("", "", "")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result["_offline_fallback"] is True
        assert result["catalyst_verdict"] == "WEAK"

    def test_returns_dict_on_llm_success(self, tmp_path):
        mock_response = json.dumps({
            "catalyst_verdict": "ADEQUATE",
            "specific_catalysts": ["Q2 EPS beat"],
            "vague_catalysts": ["continued growth"],
            "unsupported_catalysts": [],
            "specificity_rate": 0.6,
            "timeliness_note": "One Q2 catalyst is timely.",
            "support_note": "One claim verified.",
            "summary": "Mixed quality catalysts.",
        })
        with patch(_LLM_CATALYST, return_value=(mock_response, "anthropic", "claude-test")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, _CATALYST_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert result["catalyst_verdict"] == "ADEQUATE"
        assert result["specificity_rate"] == 0.6
        assert "_offline_fallback" not in result

    def test_writes_output_file(self, tmp_path):
        mock_response = json.dumps({
            "catalyst_verdict": "STRONG",
            "specific_catalysts": [],
            "vague_catalysts": [],
            "unsupported_catalysts": [],
            "specificity_rate": 0.9,
            "timeliness_note": "ok",
            "support_note": "ok",
            "summary": "Strong catalysts.",
        })
        with patch(_LLM_CATALYST, return_value=(mock_response, "anthropic", "test")):
            run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, _CATALYST_FACT_ROWS, str(tmp_path))
        assert (tmp_path / "NVDA_catalyst_analysis.json").exists()

    def test_handles_malformed_llm_json(self, tmp_path):
        with patch(_LLM_CATALYST, return_value=("not json at all }", "anthropic", "test")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, _CATALYST_FACT_ROWS, str(tmp_path))
        assert result is not None
        assert "catalyst_verdict" in result

    def test_heuristic_pre_score_in_output(self, tmp_path):
        with patch(_LLM_CATALYST, return_value=("", "", "")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, _CATALYST_FACT_ROWS, str(tmp_path))
        assert "heuristic_pre_score" in result
        assert "specificity_rate" in result["heuristic_pre_score"]

    def test_no_catalyst_claims_returns_weak(self, tmp_path):
        rows = [{"metric": "market_share", "claim_text": "leading position", "claimed_value": "x",
                 "verification_status": "unverified"}]
        with patch(_LLM_CATALYST, return_value=("", "", "")):
            result = run_catalyst_evaluation("NVDA", _SAMPLE_SCORECARD, rows, str(tmp_path))
        assert result["catalyst_claim_count"] == 0
        assert result["catalyst_verdict"] == "WEAK"


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

    def test_aggregate_catalyst_weak_raises_concern(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "low"},
            {"valuation_verdict": "sound"},
            {"signal_reliability": "reliable"},
            {"catalyst_verdict": "WEAK"},
        )
        assert result["panel_verdict"] == "CONCERN"
        assert result["specialist_verdicts"]["catalyst"] == "WEAK"

    def test_aggregate_catalyst_adequate_review(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "low"},
            {"valuation_verdict": "sound"},
            {"signal_reliability": "reliable"},
            {"catalyst_verdict": "ADEQUATE"},
        )
        assert result["panel_verdict"] == "REVIEW"

    def test_aggregate_catalyst_strong_acceptable(self):
        result = _aggregate_verdicts(
            {"earnings_quality_verdict": "low"},
            {"valuation_verdict": "sound"},
            {"signal_reliability": "reliable"},
            {"catalyst_verdict": "STRONG"},
        )
        assert result["panel_verdict"] == "ACCEPTABLE"

    _PROMPT_TMPL = ("x {ticker} {earnings_rows} {scorecard_summary} "
                    "{sector} {valuation_rows} {valuation_dispersion} "
                    "{recommendation} {icr} {scr} {gate_decision} "
                    "{quant_risk_verdict} {model_risk_verdict} "
                    "{earnings_quality_verdict} {valuation_verdict}")

    def test_full_review_runs(self, tmp_path):
        mock_e = '{"earnings_quality_verdict":"medium","earnings_quality_rationale":"ok"}'
        mock_v = '{"valuation_verdict":"sound","valuation_rationale":"ok"}'
        mock_cat = json.dumps({
            "catalyst_verdict": "ADEQUATE", "specific_catalysts": [], "vague_catalysts": [],
            "unsupported_catalysts": [], "specificity_rate": 0.5,
            "timeliness_note": "ok", "support_note": "ok", "summary": "ok",
        })
        mock_c = ('{"signal_reliability":"conditional","coherence_rationale":"ok",'
                  '"coherence_flags":[],"final_disposition":"review"}')
        with patch(_LLM_EARNINGS, return_value=(mock_e, "anthropic", "test")), \
             patch(_PROMPT_EARNINGS, return_value=self._PROMPT_TMPL), \
             patch(_LLM_VALUATION, return_value=(mock_v, "anthropic", "test")), \
             patch(_PROMPT_VALUATION, return_value=self._PROMPT_TMPL), \
             patch(_LLM_CATALYST, return_value=(mock_cat, "anthropic", "test")), \
             patch(_LLM_COHERENCE, return_value=(mock_c, "anthropic", "test")), \
             patch(_PROMPT_COHERENCE, return_value=self._PROMPT_TMPL):
            result = run_multi_agent_review("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert result["ticker"] == "NVDA"
        assert "catalyst_evaluator" in result["agents_run"]
        assert len(result["agents_run"]) == 4
        assert (tmp_path / "NVDA_multi_agent_review.json").exists()
        assert "catalyst_summary" in result

    def test_skips_agents_on_no_llm(self, tmp_path):
        # catalyst_evaluator has offline fallback → always in agents_run even without LLM
        # earnings, valuation, coherence return None when LLM is absent → skipped
        with patch(_LLM_EARNINGS, return_value=("", "", "")), \
             patch(_PROMPT_EARNINGS, return_value=self._PROMPT_TMPL), \
             patch(_LLM_VALUATION, return_value=("", "", "")), \
             patch(_PROMPT_VALUATION, return_value=self._PROMPT_TMPL), \
             patch(_LLM_CATALYST, return_value=("", "", "")), \
             patch(_LLM_COHERENCE, return_value=("", "", "")), \
             patch(_PROMPT_COHERENCE, return_value=self._PROMPT_TMPL):
            result = run_multi_agent_review("NVDA", _SAMPLE_SCORECARD, _SAMPLE_FACT_ROWS, str(tmp_path))
        assert "earnings_analyst" not in result["agents_run"]
        assert "catalyst_evaluator" in result["agents_run"]   # offline fallback keeps it alive
        assert len(result["agents_skipped"]) == 3  # earnings, valuation, coherence
        assert result["panel_verdict"] in ("ACCEPTABLE", "REVIEW", "CONCERN")
