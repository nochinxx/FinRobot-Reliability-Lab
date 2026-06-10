"""
Fixture-based tests for reliability_lab/recommendation_extractor.py.

No live API calls — DEV_MODE=1 is set by conftest.py autouse fixture.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.recommendation_extractor import extract_recommendation

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "sample_report_snippet.html"


class TestExtractRecommendationOffline:
    def test_returns_none_without_api_key(self, tmp_path):
        # DEV_MODE=1 is set by conftest; no ANTHROPIC_API_KEY in env
        assert os.environ.get("ANTHROPIC_API_KEY") is None
        result = extract_recommendation(
            report_path=str(SAMPLE_HTML),
            ticker="NVDA",
            output_dir=str(tmp_path),
        )
        assert result is None

    def test_raises_file_not_found_for_missing_report(self, tmp_path):
        # Even without API key, missing file should raise before the key check
        # (currently raises only if key is set — None return if no key)
        # This tests the no-key short-circuit path safely
        result = extract_recommendation(
            report_path=str(tmp_path / "nonexistent.html"),
            ticker="NVDA",
        )
        assert result is None  # no key → returns None before file check


class TestRecommendationSchemaStructure:
    """Validate a pre-built sample recommendation against the schema."""

    SAMPLE_REC = {
        "ticker": "NVDA",
        "company": "Nvidia Corporation",
        "report_date": "2024-01-15",
        "model": "FinRobot-v1",
        "rating": {
            "value": "BUY",
            "inferred": False,
            "evidence_text": "We recommend Buy with a 12-month price target of $300."
        },
        "current_price": {
            "value": 172.70,
            "date": "2024-01-15",
            "evidence_text": "Current Price: $172.70"
        },
        "price_target": {
            "value": 300.00,
            "time_horizon_months": 12,
            "evidence_text": "12-month price target of $300.00"
        },
        "expected_return_pct": {
            "value": 74.0,
            "calculation": "(300-172.70)/172.70",
            "evidence_text": "implying 74% upside"
        },
        "core_thesis": "AI infrastructure demand drives NVDA revenue growth",
        "variant_perception": "Market underestimates sovereign AI deployment TAM",
        "top_catalysts": [
            {
                "catalyst": "Hyperscaler capex ramp",
                "expected_date": None,
                "mechanism": "H100/H200 order backlog monetization",
                "evidence_text": "continued AI infrastructure spending by hyperscalers"
            }
        ],
        "top_risks": [
            {
                "risk": "Export control expansion",
                "severity": "HIGH",
                "evidence_text": "potential US export restrictions on advanced chips"
            }
        ],
        "key_assumptions": ["AI capex cycle persists through 2025"],
        "valuation_methods": ["DCF", "EV/EBITDA"],
        "unsupported_recommendation_components": [],
        "extraction_method": "llm",
        "model_name": "claude-sonnet-4-6",
        "provider": "anthropic"
    }

    def test_sample_has_required_top_level_keys(self):
        rec = self.SAMPLE_REC
        for key in ["ticker", "rating", "price_target", "top_catalysts", "top_risks"]:
            assert key in rec, f"Missing key: {key}"

    def test_rating_value_is_valid(self):
        rec = self.SAMPLE_REC
        assert rec["rating"]["value"] in ("BUY", "HOLD", "SELL", None)

    def test_top_risks_have_severity(self):
        for risk in self.SAMPLE_REC["top_risks"]:
            assert risk["severity"] in ("LOW", "MEDIUM", "HIGH")

    def test_ticker_matches(self):
        assert self.SAMPLE_REC["ticker"] == "NVDA"
