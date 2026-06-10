"""
Tests for reliability_lab/verifiers/fmp_verifier.py.
All tests run offline — _get_ratios, _get_cash_flow, etc. are patched directly.
DEV_MODE=1 is set by conftest.py, so live HTTP calls never happen.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.verifiers.fmp_verifier import (
    _find_by_year,
    verify_eps,
    verify_pe_ratio,
    verify_ev_ebitda,
    verify_ebitda_fmp,
    verify_net_income,
    verify_free_cash_flow,
    verify_gross_margin,
    verify_net_margin,
    verify_total_debt,
    FMP_VERIFIERS,
)

_MOD = "reliability_lab.verifiers.fmp_verifier"

# ── _find_by_year ──────────────────────────────────────────────────────────────

class TestFindByYear:
    def test_matches_fiscal_year_fy(self):
        records = [{"fiscalYear": "2023", "period": "FY", "val": 1}]
        assert _find_by_year(records, 2023) == records[0]

    def test_matches_fiscal_year_annual(self):
        records = [{"fiscalYear": "2022", "period": "annual", "val": 2}]
        assert _find_by_year(records, 2022) == records[0]

    def test_matches_fiscal_year_no_period(self):
        records = [{"fiscalYear": "2021", "val": 3}]
        assert _find_by_year(records, 2021) == records[0]

    def test_falls_back_to_date_prefix(self):
        records = [{"date": "2022-12-31", "val": 10}]
        assert _find_by_year(records, 2022) == records[0]

    def test_returns_none_when_no_match(self):
        records = [{"fiscalYear": "2020", "period": "FY", "val": 5}]
        assert _find_by_year(records, 2023) is None

    def test_returns_none_on_empty(self):
        assert _find_by_year([], 2023) is None

    def test_prefers_fiscal_year_over_date(self):
        records = [
            {"fiscalYear": "2023", "period": "FY", "val": "fy"},
            {"date": "2023-06-30", "val": "date"},
        ]
        assert _find_by_year(records, 2023)["val"] == "fy"


# ── verify_eps ─────────────────────────────────────────────────────────────────

class TestVerifyEps:
    _RATIOS = [{"fiscalYear": "2023", "period": "FY", "netIncomePerShare": 6.5}]

    def test_verified_within_tolerance(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            v, status, src = verify_eps("AAPL", "2023", 6.5)
        assert status == "verified"
        assert "6.50" in v

    def test_incorrect_outside_tolerance(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            v, status, src = verify_eps("AAPL", "2023", 10.0)
        assert status == "incorrect"

    def test_not_verifiable_when_empty_ratios(self):
        with patch(f"{_MOD}._get_ratios", return_value=[]):
            _, status, _ = verify_eps("AAPL", "2023", 6.5)
        assert status == "not_machine_verifiable"

    def test_not_verifiable_when_year_missing(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            _, status, _ = verify_eps("AAPL", "2020", 6.5)
        assert status == "not_machine_verifiable"

    def test_not_verifiable_on_empty_period(self):
        _, status, _ = verify_eps("AAPL", "", 6.5)
        assert status == "not_machine_verifiable"

    def test_not_verifiable_missing_field(self):
        ratios = [{"fiscalYear": "2023", "period": "FY"}]
        with patch(f"{_MOD}._get_ratios", return_value=ratios):
            _, status, _ = verify_eps("AAPL", "2023", 6.5)
        assert status == "not_machine_verifiable"


# ── verify_pe_ratio ────────────────────────────────────────────────────────────

class TestVerifyPeRatio:
    _RATIOS = [{"fiscalYear": "2023", "period": "FY", "priceToEarningsRatio": 25.0}]

    def test_verified_within_tolerance(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            v, status, _ = verify_pe_ratio("MSFT", "2023", 25.0)
        assert status == "verified"
        assert "25.0x" in v

    def test_incorrect_outside_tolerance(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            _, status, _ = verify_pe_ratio("MSFT", "2023", 40.0)
        assert status == "incorrect"

    def test_negative_pe_returns_nmv(self):
        ratios = [{"fiscalYear": "2023", "period": "FY", "priceToEarningsRatio": -5.0}]
        with patch(f"{_MOD}._get_ratios", return_value=ratios):
            _, status, _ = verify_pe_ratio("RIVN", "2023", 10.0)
        assert status == "not_machine_verifiable"

    def test_empty_ratios_returns_nmv(self):
        with patch(f"{_MOD}._get_ratios", return_value=[]):
            _, status, _ = verify_pe_ratio("MSFT", "2023", 25.0)
        assert status == "not_machine_verifiable"

    def test_missing_field_returns_nmv(self):
        ratios = [{"fiscalYear": "2023", "period": "FY"}]
        with patch(f"{_MOD}._get_ratios", return_value=ratios):
            _, status, _ = verify_pe_ratio("MSFT", "2023", 25.0)
        assert status == "not_machine_verifiable"


# ── verify_ev_ebitda ───────────────────────────────────────────────────────────

class TestVerifyEvEbitda:
    _RATIOS = [{"fiscalYear": "2022", "period": "FY", "enterpriseValueMultiple": 18.0}]
    _METRICS = [{"fiscalYear": "2022", "period": "FY", "evToEBITDA": 18.0}]

    def test_verified_from_ratios(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS), \
             patch(f"{_MOD}._get_key_metrics", return_value=[]):
            v, status, _ = verify_ev_ebitda("NVDA", "2022", 18.0)
        assert status == "verified"

    def test_falls_back_to_key_metrics(self):
        with patch(f"{_MOD}._get_ratios", return_value=[]), \
             patch(f"{_MOD}._get_key_metrics", return_value=self._METRICS):
            v, status, _ = verify_ev_ebitda("NVDA", "2022", 18.0)
        assert status == "verified"

    def test_nmv_when_both_missing(self):
        with patch(f"{_MOD}._get_ratios", return_value=[]), \
             patch(f"{_MOD}._get_key_metrics", return_value=[]):
            _, status, _ = verify_ev_ebitda("NVDA", "2022", 18.0)
        assert status == "not_machine_verifiable"

    def test_incorrect_outside_tolerance(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS), \
             patch(f"{_MOD}._get_key_metrics", return_value=[]):
            _, status, _ = verify_ev_ebitda("NVDA", "2022", 50.0)
        assert status == "incorrect"


# ── verify_ebitda_fmp ──────────────────────────────────────────────────────────

class TestVerifyEbitdaFmp:
    _CF = [{"fiscalYear": "2023", "period": "FY",
            "netIncome": 30_000_000_000, "depreciationAndAmortization": 5_000_000_000}]

    def test_verified_within_tolerance(self):
        # approx = 35B; claimed 35B → verified
        with patch(f"{_MOD}._get_cash_flow", return_value=self._CF):
            v, status, _ = verify_ebitda_fmp("META", "2023", 35e9)
        assert status == "verified"
        assert "35.00" in v

    def test_incorrect_outside_tolerance(self):
        with patch(f"{_MOD}._get_cash_flow", return_value=self._CF):
            _, status, _ = verify_ebitda_fmp("META", "2023", 60e9)
        assert status == "incorrect"

    def test_empty_cash_flow_returns_nmv(self):
        with patch(f"{_MOD}._get_cash_flow", return_value=[]):
            _, status, _ = verify_ebitda_fmp("META", "2023", 35e9)
        assert status == "not_machine_verifiable"

    def test_missing_fields_returns_nmv(self):
        cf = [{"fiscalYear": "2023", "period": "FY"}]
        with patch(f"{_MOD}._get_cash_flow", return_value=cf):
            _, status, _ = verify_ebitda_fmp("META", "2023", 35e9)
        assert status == "not_machine_verifiable"


# ── verify_net_income ──────────────────────────────────────────────────────────

class TestVerifyNetIncome:
    _CF = [{"fiscalYear": "2023", "period": "FY", "netIncome": 20_000_000_000}]

    def test_verified(self):
        with patch(f"{_MOD}._get_cash_flow", return_value=self._CF):
            v, status, _ = verify_net_income("AAPL", "2023", 20e9)
        assert status == "verified"

    def test_nmv_on_empty_cf(self):
        with patch(f"{_MOD}._get_cash_flow", return_value=[]):
            _, status, _ = verify_net_income("AAPL", "2023", 20e9)
        assert status == "not_machine_verifiable"


# ── verify_free_cash_flow ──────────────────────────────────────────────────────

class TestVerifyFreeCashFlow:
    _CF = [{"fiscalYear": "2023", "period": "FY", "freeCashFlow": 15_000_000_000}]

    def test_verified(self):
        with patch(f"{_MOD}._get_cash_flow", return_value=self._CF):
            v, status, _ = verify_free_cash_flow("AAPL", "2023", 15e9)
        assert status == "verified"

    def test_nmv_on_missing_field(self):
        cf = [{"fiscalYear": "2023", "period": "FY"}]
        with patch(f"{_MOD}._get_cash_flow", return_value=cf):
            _, status, _ = verify_free_cash_flow("AAPL", "2023", 15e9)
        assert status == "not_machine_verifiable"


# ── verify_gross_margin ────────────────────────────────────────────────────────

class TestVerifyGrossMargin:
    _RATIOS = [{"fiscalYear": "2023", "period": "FY", "grossProfitMargin": 0.60}]

    def test_verified_converts_decimal(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            v, status, _ = verify_gross_margin("NVDA", "2023", 60.0)
        assert status == "verified"
        assert "60.0%" in v

    def test_incorrect_on_wrong_value(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            _, status, _ = verify_gross_margin("NVDA", "2023", 30.0)
        assert status == "incorrect"


# ── verify_net_margin ──────────────────────────────────────────────────────────

class TestVerifyNetMargin:
    _RATIOS = [{"fiscalYear": "2022", "period": "FY", "netProfitMargin": 0.25}]

    def test_verified(self):
        with patch(f"{_MOD}._get_ratios", return_value=self._RATIOS):
            v, status, _ = verify_net_margin("MSFT", "2022", 25.0)
        assert status == "verified"


# ── verify_total_debt ──────────────────────────────────────────────────────────

class TestVerifyTotalDebt:
    _BS = [{"fiscalYear": "2023", "period": "FY", "totalDebt": 50_000_000_000}]

    def test_verified(self):
        with patch(f"{_MOD}._get_balance_sheet", return_value=self._BS):
            v, status, _ = verify_total_debt("TSLA", "2023", 50e9)
        assert status == "verified"

    def test_nmv_on_empty(self):
        with patch(f"{_MOD}._get_balance_sheet", return_value=[]):
            _, status, _ = verify_total_debt("TSLA", "2023", 50e9)
        assert status == "not_machine_verifiable"


# ── FMP_VERIFIERS dispatch table ───────────────────────────────────────────────

class TestFmpVerifiersDispatch:
    def test_all_expected_keys_present(self):
        expected = {"eps", "pe_ratio", "ev_ebitda", "ebitda", "net_income",
                    "free_cash_flow", "gross_margin", "net_margin",
                    "market_cap", "total_debt", "revenue_growth",
                    "ebitda_margin", "growth_rate"}
        assert expected.issubset(set(FMP_VERIFIERS.keys()))

    def test_all_values_are_callable(self):
        for key, fn in FMP_VERIFIERS.items():
            assert callable(fn), f"FMP_VERIFIERS[{key!r}] is not callable"
