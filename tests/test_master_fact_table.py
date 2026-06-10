"""
Tests for reliability_lab/master_fact_table.py.

Fixture-based, no API calls. Tests master_status mapping and merge logic.
"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.master_fact_table import (
    merge_fact_tables,
    save_master_fact_table,
    status_summary,
    _master_status,
    MASTER_COLUMNS,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _row(status, tier="", source=""):
    return {"verification_status": status, "source_tier": tier, "source": source,
            "ticker": "NVDA", "claim_type": "financial", "metric": "revenue",
            "period": "2023", "claimed_value": "$27B", "verified_value": "$26.97B",
            "notes": "", "verified_value_alt": "", "source_alt": "", "conflict_details": ""}


def _write_fixture_csv(path: Path, rows: list[dict]):
    from reliability_lab.fact_table_builder import FACT_TABLE_COLUMNS
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FACT_TABLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── Master status mapping ──────────────────────────────────────────────────────

class TestMasterStatusMapping:
    def test_verified_tier1_gives_locked(self):
        row = _row("verified", tier="1", source="SEC EDGAR 10-K")
        assert _master_status(row) == "LOCKED"

    def test_verified_tier1_sec_ebitda_source_gives_locked(self):
        row = _row("verified", tier="1", source="SEC EDGAR 10-K (op. income + D&A)")
        assert _master_status(row) == "LOCKED"

    def test_verified_tier3_gives_provisional(self):
        row = _row("verified", tier="3", source="FMP ratios FY2023")
        assert _master_status(row) == "PROVISIONAL"

    def test_verified_no_tier_gives_provisional(self):
        row = _row("verified", tier="", source="FMP ratios FY2023")
        assert _master_status(row) == "PROVISIONAL"

    def test_source_conflict_gives_conflict(self):
        row = _row("SOURCE_CONFLICT", tier="1", source="SEC EDGAR 10-K")
        assert _master_status(row) == "CONFLICT"

    def test_incorrect_gives_incorrect(self):
        row = _row("incorrect", tier="3", source="FMP ratios FY2023")
        assert _master_status(row) == "INCORRECT"

    def test_unsupported_gives_unverified(self):
        row = _row("unsupported", tier="", source="")
        assert _master_status(row) == "UNVERIFIED"

    def test_not_machine_verifiable_gives_unverified(self):
        row = _row("not_machine_verifiable", tier="", source="forward-looking")
        assert _master_status(row) == "UNVERIFIED"


# ── Status summary ─────────────────────────────────────────────────────────────

class TestStatusSummary:
    def test_counts_correct(self):
        rows = [
            {**_row("verified", "1"), "master_status": "LOCKED"},
            {**_row("verified", "3"), "master_status": "PROVISIONAL"},
            {**_row("SOURCE_CONFLICT", "1"), "master_status": "CONFLICT"},
            {**_row("incorrect", "3"), "master_status": "INCORRECT"},
            {**_row("unsupported", ""), "master_status": "UNVERIFIED"},
        ]
        s = status_summary(rows)
        assert s["LOCKED"] == 1
        assert s["PROVISIONAL"] == 1
        assert s["CONFLICT"] == 1
        assert s["INCORRECT"] == 1
        assert s["UNVERIFIED"] == 1
        assert s["total"] == 5

    def test_all_locked(self):
        rows = [{**_row("verified", "1"), "master_status": "LOCKED"} for _ in range(4)]
        s = status_summary(rows)
        assert s["LOCKED"] == 4
        assert s["total"] == 4

    def test_empty_rows(self):
        s = status_summary([])
        assert s["total"] == 0


# ── Merge from CSV fixtures ────────────────────────────────────────────────────

class TestMergeFactTables:
    def test_merge_single_ticker(self, tmp_path):
        csv_path = tmp_path / "NVDA" / "NVDA_fact_table.csv"
        rows = [_row("verified", "1", "SEC EDGAR 10-K")]
        _write_fixture_csv(csv_path, rows)

        merged = merge_fact_tables(["NVDA"], base_output_dir=str(tmp_path))
        assert len(merged) == 1
        assert merged[0]["master_status"] == "LOCKED"

    def test_merge_missing_ticker_skipped(self, tmp_path):
        merged = merge_fact_tables(["NOTEXIST"], base_output_dir=str(tmp_path))
        assert merged == []

    def test_merge_multiple_tickers(self, tmp_path):
        for ticker, status in [("NVDA", "verified"), ("TSLA", "unsupported")]:
            tier = "1" if status == "verified" else ""
            src  = "SEC EDGAR 10-K" if status == "verified" else ""
            path = tmp_path / ticker / f"{ticker}_fact_table.csv"
            row = {**_row(status, tier, src), "ticker": ticker}
            _write_fixture_csv(path, [row])

        merged = merge_fact_tables(["NVDA", "TSLA"], base_output_dir=str(tmp_path))
        assert len(merged) == 2
        tickers = {r["ticker"] for r in merged}
        assert tickers == {"NVDA", "TSLA"}

    def test_merged_rows_have_all_master_columns(self, tmp_path):
        csv_path = tmp_path / "NVDA" / "NVDA_fact_table.csv"
        _write_fixture_csv(csv_path, [_row("verified", "1", "SEC EDGAR 10-K")])
        merged = merge_fact_tables(["NVDA"], base_output_dir=str(tmp_path))
        for col in MASTER_COLUMNS:
            assert col in merged[0], f"Missing column: {col}"

    def test_conflict_rows_mapped_correctly(self, tmp_path):
        csv_path = tmp_path / "NVDA" / "NVDA_fact_table.csv"
        _write_fixture_csv(csv_path, [_row("SOURCE_CONFLICT", "1", "SEC EDGAR 10-K")])
        merged = merge_fact_tables(["NVDA"], base_output_dir=str(tmp_path))
        assert merged[0]["master_status"] == "CONFLICT"


# ── Save master fact table ─────────────────────────────────────────────────────

class TestSaveMasterFactTable:
    def test_save_creates_file(self, tmp_path):
        rows = [{**_row("verified", "1", "SEC EDGAR 10-K"), "master_status": "LOCKED"}]
        path = save_master_fact_table(rows, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "master_fact_table.csv"

    def test_saved_csv_has_master_status_column(self, tmp_path):
        rows = [{**_row("verified", "1", "SEC EDGAR 10-K"), "master_status": "LOCKED"}]
        path = save_master_fact_table(rows, output_dir=str(tmp_path))
        with open(path) as f:
            header = f.readline()
        assert "master_status" in header

    def test_save_empty_rows(self, tmp_path):
        path = save_master_fact_table([], output_dir=str(tmp_path))
        assert path.exists()
