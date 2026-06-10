"""
Tests for reliability_lab/report/annotated_report.py and run_master_fact_table.py.
No live API calls. Tests verify HTML structure and CLI correctness.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.report.annotated_report import generate_annotated_report, _esc, _badge


# ── Helpers ────────────────────────────────────────────────────────────────────

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
        },
    }


def _fact_rows():
    return [
        {"metric": "revenue", "period": "2023", "claimed_value": "$27B",
         "verified_value": "$26.97B", "source": "SEC EDGAR 10-K",
         "source_tier": "1", "verification_status": "verified",
         "verified_value_alt": "", "source_alt": "", "conflict_details": "", "notes": ""},
        {"metric": "pe_ratio", "period": "2023", "claimed_value": "37.7x",
         "verified_value": "30.0x", "source": "FMP ratios FY2023",
         "source_tier": "3", "verification_status": "incorrect",
         "verified_value_alt": "", "source_alt": "", "conflict_details": "", "notes": ""},
        {"metric": "ebitda", "period": "2023", "claimed_value": "$20B",
         "verified_value": "$18B (op.income+D&A)", "source": "SEC EDGAR 10-K",
         "source_tier": "1", "verification_status": "SOURCE_CONFLICT",
         "verified_value_alt": "$19B (net income+D&A)", "source_alt": "FMP cash-flow FY2023",
         "conflict_details": json.dumps({"tier1_value": "$18B", "tier3_value": "$19B",
                                          "delta_pct": 0.055, "tolerance": 0.15}),
         "notes": ""},
        {"metric": "revenue", "period": "2025", "claimed_value": "$100B",
         "verified_value": "", "source": "forward projection",
         "source_tier": "", "verification_status": "not_machine_verifiable",
         "verified_value_alt": "", "source_alt": "", "conflict_details": "", "notes": ""},
    ]


# ── HTML generation ────────────────────────────────────────────────────────────

class TestAnnotatedReportGeneration:
    def test_creates_html_file(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        assert path.exists()
        assert path.suffix == ".html"
        assert path.name == "NVDA_annotated_report.html"

    def test_html_has_ticker_in_title(self, tmp_path):
        path = generate_annotated_report("TSLA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert "TSLA" in html

    def test_html_has_all_status_types(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert "VERIFIED" in html
        assert "INCORRECT" in html
        assert "CONFLICT" in html
        assert "NMV" in html

    def test_html_has_scorecard_metrics(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert "Source Coverage Rate" in html or "SCR" in html
        assert "Incorrect Claim Rate" in html or "ICR" in html

    def test_html_shows_conflict_detail(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert "SOURCE_CONFLICT" in html or "CONFLICT" in html
        assert "Tier1" in html or "Tier 1" in html

    def test_html_with_gate_decision(self, tmp_path):
        gate = {
            "decision": "HUMAN_REVIEW",
            "human_review_triggers": ["icr_above_target"],
            "hard_failures": [],
            "reasons": [],
        }
        path = generate_annotated_report(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path), gate=gate
        )
        html = path.read_text()
        assert "HUMAN_REVIEW" in html

    def test_html_pass_gate_shows_green(self, tmp_path):
        gate = {"decision": "PASS", "human_review_triggers": [], "hard_failures": [], "reasons": []}
        path = generate_annotated_report(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path), gate=gate
        )
        html = path.read_text()
        assert "PASS" in html

    def test_html_fail_gate(self, tmp_path):
        gate = {
            "decision": "FAIL",
            "human_review_triggers": [],
            "hard_failures": ["icr_0.200_exceeds_fail_threshold"],
            "reasons": [],
        }
        path = generate_annotated_report(
            "NVDA", _scorecard(icr=0.20), _fact_rows(), str(tmp_path), gate=gate
        )
        html = path.read_text()
        assert "FAIL" in html

    def test_html_no_gate_shows_placeholder(self, tmp_path):
        path = generate_annotated_report(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path), gate=None
        )
        html = path.read_text()
        assert "not run" in html or "use --gate" in html

    def test_html_empty_fact_rows(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), [], str(tmp_path))
        assert path.exists()
        html = path.read_text()
        assert "0 claims" in html

    def test_html_report_path_shown(self, tmp_path):
        path = generate_annotated_report(
            "NVDA", _scorecard(), _fact_rows(), str(tmp_path),
            report_path="finrobot_equity/core/output/NVDA_report.html"
        )
        html = path.read_text()
        assert "NVDA_report.html" in html

    def test_html_is_valid_structure(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert html.startswith("<!DOCTYPE html>")
        assert "<html" in html
        assert "</html>" in html
        assert "<body>" in html
        assert "</body>" in html

    def test_by_metric_breakdown_present(self, tmp_path):
        path = generate_annotated_report("NVDA", _scorecard(), _fact_rows(), str(tmp_path))
        html = path.read_text()
        assert "Per-Metric" in html
        assert "revenue" in html

    def test_xss_characters_escaped(self, tmp_path):
        rows = [{
            "metric": "<script>alert(1)</script>",
            "period": "2023", "claimed_value": "$1B",
            "verified_value": "", "source": "",
            "source_tier": "", "verification_status": "unsupported",
            "verified_value_alt": "", "source_alt": "", "conflict_details": "", "notes": "",
        }]
        path = generate_annotated_report("NVDA", _scorecard(), rows, str(tmp_path))
        html = path.read_text()
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


# ── Utility functions ──────────────────────────────────────────────────────────

class TestUtilityFunctions:
    def test_esc_ampersand(self):
        assert "&amp;" in _esc("a & b")

    def test_esc_lt(self):
        assert "&lt;" in _esc("<div>")

    def test_esc_gt(self):
        assert "&gt;" in _esc(">")

    def test_esc_none_safe(self):
        assert _esc(None) == ""

    def test_badge_verified(self):
        b = _badge("verified")
        assert "VERIFIED" in b
        assert "badge" in b

    def test_badge_incorrect(self):
        b = _badge("incorrect")
        assert "INCORRECT" in b

    def test_badge_unknown_status(self):
        b = _badge("some_new_status")
        assert "badge" in b  # still renders something


# ── Master fact table CLI (smoke test) ────────────────────────────────────────

class TestMasterFactTableCLI:
    def test_run_master_fact_table_no_tickers(self, tmp_path, capsys):
        from run_master_fact_table import _discover_tickers
        result = _discover_tickers(str(tmp_path))
        assert result == []

    def test_run_master_fact_table_discovers_csv(self, tmp_path):
        from run_master_fact_table import _discover_tickers
        from reliability_lab.fact_table_builder import FACT_TABLE_COLUMNS
        # Create fake fact table
        ticker_dir = tmp_path / "NVDA"
        ticker_dir.mkdir()
        csv_path = ticker_dir / "NVDA_fact_table.csv"
        with open(csv_path, "w") as f:
            writer = csv.DictWriter(f, fieldnames=FACT_TABLE_COLUMNS)
            writer.writeheader()
        result = _discover_tickers(str(tmp_path))
        assert "NVDA" in result

    def test_merge_and_save_produces_csv(self, tmp_path):
        from reliability_lab.fact_table_builder import FACT_TABLE_COLUMNS
        from reliability_lab.master_fact_table import merge_fact_tables, save_master_fact_table
        ticker_dir = tmp_path / "NVDA"
        ticker_dir.mkdir()
        csv_path = ticker_dir / "NVDA_fact_table.csv"
        row = {c: "" for c in FACT_TABLE_COLUMNS}
        row.update({"ticker": "NVDA", "metric": "revenue", "period": "2023",
                    "claimed_value": "$27B", "verified_value": "$26.97B",
                    "source": "SEC EDGAR 10-K", "source_tier": "1",
                    "verification_status": "verified"})
        with open(csv_path, "w") as f:
            writer = csv.DictWriter(f, fieldnames=FACT_TABLE_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows([row])
        merged = merge_fact_tables(["NVDA"], base_output_dir=str(tmp_path))
        out = save_master_fact_table(merged, output_dir=str(tmp_path))
        assert out.exists()
        assert out.name == "master_fact_table.csv"
        with open(out) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["master_status"] == "LOCKED"
