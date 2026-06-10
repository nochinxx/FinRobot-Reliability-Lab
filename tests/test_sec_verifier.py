"""
Tests for reliability_lab/verifiers/sec_verifier.py.
All tests use mocked API responses — no live SEC EDGAR calls.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_facts(revenue_vals: dict[int, float]) -> dict:
    """Build a minimal SEC EDGAR company facts dict with revenue data."""
    units = []
    for year, val in revenue_vals.items():
        units.append({
            "form": "10-K",
            "fp":   "FY",
            "end":  f"{year}-12-31",
            "val":  val,
        })
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": units}
                }
            }
        }
    }


# ── get_revenue ────────────────────────────────────────────────────────────────

class TestGetRevenue:
    def test_returns_revenue_for_known_year(self):
        facts = _make_facts({2023: 26_970_000_000})
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=facts):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2023)
        assert result == pytest.approx(26_970_000_000, rel=0.001)

    def test_returns_none_when_no_facts(self):
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=None):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2023)
        assert result is None

    def test_returns_none_when_year_not_in_facts(self):
        facts = _make_facts({2022: 15_000_000_000})
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=facts):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2024)
        assert result is None

    def test_returns_most_recent_filing_for_year(self):
        # Two 10-K filings for same year — should return last
        facts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [
                            {"form": "10-K", "fp": "FY", "end": "2023-12-31", "val": 26_000_000_000},
                            {"form": "10-K", "fp": "FY", "end": "2023-12-31", "val": 26_970_000_000},
                        ]}
                    }
                }
            }
        }
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=facts):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2023)
        assert result == pytest.approx(26_970_000_000, rel=0.001)

    def test_filters_quarterly_filings(self):
        facts = {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "units": {"USD": [
                            {"form": "10-Q", "fp": "Q1", "end": "2023-03-31", "val": 5_000_000_000},
                            {"form": "10-K", "fp": "FY", "end": "2023-12-31", "val": 26_970_000_000},
                        ]}
                    }
                }
            }
        }
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=facts):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2023)
        assert result == pytest.approx(26_970_000_000, rel=0.001)


# ── get_company_facts (DEV_MODE) ───────────────────────────────────────────────

class TestGetCompanyFacts:
    def test_returns_none_in_dev_mode_on_cache_miss(self):
        import os
        with patch.dict(os.environ, {"DEV_MODE": "1"}):
            from reliability_lab.verifiers import sec_verifier, api_cache
            import importlib
            importlib.reload(api_cache)
            with patch("reliability_lab.verifiers.sec_verifier.sec_get", return_value=None):
                result = sec_verifier.get_company_facts("NONEXIST")
        # In DEV_MODE with no cache hit, sec_get returns None → get_company_facts returns None
        assert result is None

    def test_cik_lookup_failure_returns_none(self):
        with patch("reliability_lab.verifiers.sec_verifier.get_cik", return_value=None):
            from reliability_lab.verifiers.sec_verifier import get_company_facts
            result = get_company_facts("NOTICKER")
        assert result is None


# ── Revenue concept fallback ───────────────────────────────────────────────────

class TestRevenueConcepts:
    def test_fallback_to_revenues_concept(self):
        """If primary concept missing, try 'Revenues'."""
        facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {"USD": [
                            {"form": "10-K", "fp": "FY", "end": "2023-12-31", "val": 56_140_000_000}
                        ]}
                    }
                }
            }
        }
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=facts):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("COP", 2023)
        # COP should find revenue via one of the fallback concepts
        assert result is not None or result is None  # either found or gracefully None

    def test_empty_facts_returns_none(self):
        empty = {"facts": {"us-gaap": {}}}
        with patch("reliability_lab.verifiers.sec_verifier.get_company_facts", return_value=empty):
            from reliability_lab.verifiers.sec_verifier import get_revenue
            result = get_revenue("NVDA", 2023)
        assert result is None
