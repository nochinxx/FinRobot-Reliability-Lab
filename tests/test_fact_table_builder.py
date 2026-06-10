"""
Tests for reliability_lab/fact_table_builder.py.
All tests run offline — SEC/FMP calls are patched.
DEV_MODE=1 is set by conftest.py.
"""
import csv
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.fact_table_builder import (
    FACT_TABLE_COLUMNS,
    VERIFICATION_STATUSES,
    _check_source_conflict,
    _verify_claim,
    build_and_verify_fact_table,
    save_fact_table,
)

_SEC_MOD = "reliability_lab.fact_table_builder.get_revenue"
_SEC_FACTS_MOD = "reliability_lab.fact_table_builder.get_company_facts"
_FMP_EPS = "reliability_lab.fact_table_builder.verify_eps"
_FMP_PE = "reliability_lab.fact_table_builder.verify_pe_ratio"
_FMP_EV = "reliability_lab.fact_table_builder.verify_ev_ebitda"


# ── FACT_TABLE_COLUMNS / VERIFICATION_STATUSES ─────────────────────────────────

class TestConstants:
    def test_fact_table_columns_complete(self):
        expected = {
            "ticker", "claim_type", "metric", "period",
            "claimed_value", "verified_value", "source",
            "source_tier", "verification_status",
            "verified_value_alt", "source_alt", "conflict_details", "notes",
        }
        assert expected == set(FACT_TABLE_COLUMNS)

    def test_fact_table_columns_ordered(self):
        assert FACT_TABLE_COLUMNS[0] == "ticker"
        assert FACT_TABLE_COLUMNS[-1] == "notes"

    def test_verification_statuses_complete(self):
        expected = {
            "verified", "incorrect", "unsupported",
            "not_machine_verifiable", "SOURCE_CONFLICT",
        }
        assert expected == set(VERIFICATION_STATUSES)


# ── _check_source_conflict ─────────────────────────────────────────────────────

class TestCheckSourceConflict:
    def test_no_conflict_within_tolerance(self):
        result = _check_source_conflict(
            100.0, 105.0, 0.15,
            "$100B", "SEC", "$105B", "FMP"
        )
        vv, src, tier, status, vv_alt, src_alt, cd = result
        assert status == "verified"
        assert vv == "$100B"
        assert src == "SEC"
        assert tier == "1"
        assert vv_alt == ""

    def test_conflict_outside_tolerance(self):
        result = _check_source_conflict(
            100.0, 150.0, 0.15,
            "$100B", "SEC", "$150B", "FMP"
        )
        vv, src, tier, status, vv_alt, src_alt, cd = result
        assert status == "SOURCE_CONFLICT"
        assert vv == "$100B"         # Tier 1 wins
        assert vv_alt == "$150B"     # Tier 3 recorded
        details = json.loads(cd)
        assert details["delta_pct"] > 0.15

    def test_tier1_always_wins_in_conflict(self):
        result = _check_source_conflict(
            50.0, 90.0, 0.10,
            "$50B", "SEC EDGAR", "$90B", "FMP"
        )
        _, src, tier, _, _, _, _ = result
        assert "SEC" in src
        assert tier == "1"


# ── _verify_claim routing ──────────────────────────────────────────────────────

class TestVerifyClaimRouting:
    def _base_claim(self, **kwargs):
        base = {
            "ticker": "NVDA", "metric": "revenue", "period": "2023",
            "claim_type": "quantitative", "value": 26.97e9,
            "value_display": "$26.97B", "claim_text": "NVDA generated...",
        }
        base.update(kwargs)
        return base

    def test_guidance_claim_not_verifiable(self):
        claim = self._base_claim(claim_type="guidance")
        row = _verify_claim(claim)
        assert row["verification_status"] == "not_machine_verifiable"
        assert "forward" in row["source"].lower()

    def test_peer_comparison_not_verifiable(self):
        claim = self._base_claim(claim_type="peer-comparison")
        row = _verify_claim(claim)
        assert row["verification_status"] == "not_machine_verifiable"

    def test_future_year_not_verifiable(self):
        claim = self._base_claim(period="2027")
        row = _verify_claim(claim)
        assert row["verification_status"] == "not_machine_verifiable"
        assert "2027" in row["source"]

    def test_none_value_returns_unsupported(self):
        claim = self._base_claim(value=None)
        row = _verify_claim(claim)
        assert row["verification_status"] == "unsupported"

    def test_revenue_routes_to_sec(self):
        with patch(_SEC_MOD, return_value=26.97e9):
            row = _verify_claim(self._base_claim(metric="revenue", period="2023"))
        assert row["verification_status"] == "verified"
        assert row["source_tier"] == "1"

    def test_revenue_incorrect_when_wrong(self):
        with patch(_SEC_MOD, return_value=50e9):
            row = _verify_claim(self._base_claim(metric="revenue", period="2023"))
        assert row["verification_status"] == "incorrect"

    def test_revenue_nmv_when_sec_returns_none(self):
        with patch(_SEC_MOD, return_value=None):
            row = _verify_claim(self._base_claim(metric="revenue", period="2023"))
        assert row["verification_status"] == "not_machine_verifiable"

    def test_eps_routes_to_fmp(self):
        with patch(_FMP_EPS, return_value=("$6.50", "verified", "FMP FY2023")):
            row = _verify_claim(self._base_claim(metric="eps", value=6.5))
        assert row["verification_status"] == "verified"
        assert row["source_tier"] == "3"

    def test_pe_ratio_routes_to_fmp(self):
        with patch(_FMP_PE, return_value=("25.0x", "verified", "FMP FY2023")):
            row = _verify_claim(self._base_claim(metric="pe_ratio", value=25.0))
        assert row["verification_status"] == "verified"

    def test_ev_ebitda_routes_to_fmp(self):
        with patch(_FMP_EV, return_value=("18.0x", "verified", "FMP FY2023")):
            row = _verify_claim(self._base_claim(metric="ev_ebitda", value=18.0))
        assert row["verification_status"] == "verified"

    def test_unknown_metric_not_verifiable(self):
        row = _verify_claim(self._base_claim(metric="unknown_kpi_xyz"))
        assert row["verification_status"] == "not_machine_verifiable"

    def test_percent_metric_with_no_verifier(self):
        claim = self._base_claim(metric="arbitrary_ratio", unit="percent")
        row = _verify_claim(claim)
        assert row["verification_status"] == "not_machine_verifiable"

    def test_output_row_has_all_columns(self):
        with patch(_SEC_MOD, return_value=26.97e9):
            row = _verify_claim(self._base_claim())
        for col in FACT_TABLE_COLUMNS:
            assert col in row, f"Column {col!r} missing from row"

    def test_notes_truncated_to_200_chars(self):
        long_text = "x" * 500
        row = _verify_claim(self._base_claim(claim_text=long_text))
        assert len(row["notes"]) <= 200


# ── build_and_verify_fact_table ────────────────────────────────────────────────

class TestBuildAndVerifyFactTable:
    def test_returns_list_of_rows(self):
        claims = [
            {"ticker": "AAPL", "metric": "revenue", "period": "2023",
             "claim_type": "quantitative", "value": 10e9, "value_display": "$10B",
             "claim_text": "test"},
        ]
        with patch(_SEC_MOD, return_value=None):
            rows = build_and_verify_fact_table(claims, "AAPL")
        assert len(rows) == 1
        assert isinstance(rows[0], dict)

    def test_empty_claims_returns_empty_list(self):
        assert build_and_verify_fact_table([], "AAPL") == []

    def test_all_rows_have_all_columns(self):
        claims = [
            {"ticker": "NVDA", "metric": "guidance_x", "period": "2023",
             "claim_type": "guidance", "value": 99.0, "value_display": "99",
             "claim_text": "forward"},
        ]
        rows = build_and_verify_fact_table(claims, "NVDA")
        for col in FACT_TABLE_COLUMNS:
            assert col in rows[0]


# ── save_fact_table ────────────────────────────────────────────────────────────

class TestSaveFactTable:
    def test_creates_csv_file(self, tmp_path):
        rows = [
            {col: "" for col in FACT_TABLE_COLUMNS}
        ]
        rows[0]["ticker"] = "NVDA"
        rows[0]["metric"] = "revenue"
        out = save_fact_table(rows, str(tmp_path), "NVDA")
        assert out.exists()
        assert out.name == "NVDA_fact_table.csv"

    def test_csv_has_correct_headers(self, tmp_path):
        rows = [{col: "val" for col in FACT_TABLE_COLUMNS}]
        out = save_fact_table(rows, str(tmp_path), "AAPL")
        with open(out) as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
        assert list(headers) == FACT_TABLE_COLUMNS

    def test_csv_data_round_trips(self, tmp_path):
        rows = [{col: "" for col in FACT_TABLE_COLUMNS}]
        rows[0]["ticker"] = "TSLA"
        rows[0]["verification_status"] = "verified"
        out = save_fact_table(rows, str(tmp_path), "TSLA")
        with open(out) as f:
            reader = csv.DictReader(f)
            data = list(reader)
        assert data[0]["ticker"] == "TSLA"
        assert data[0]["verification_status"] == "verified"

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "path"
        rows = [{col: "" for col in FACT_TABLE_COLUMNS}]
        out = save_fact_table(rows, str(nested), "COP")
        assert out.exists()
