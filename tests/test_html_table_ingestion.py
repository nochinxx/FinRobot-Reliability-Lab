"""
Tests for reliability_lab/ingestion/html_tables.py.

All tests use inline HTML or the existing fixture — no API calls, no files needed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.ingestion.html_tables import (
    table_claims_from_report,
    _normalize_period,
    _normalize_metric,
    HAS_PARSER,
)

pytestmark = pytest.mark.skipif(
    not HAS_PARSER,
    reason="BeautifulSoup / html_table_parser not available"
)


# ── Period normalization ───────────────────────────────────────────────────────

class TestNormalizePeriod:
    def test_bare_year(self):
        assert _normalize_period("2023") == "2023"

    def test_year_with_A_suffix(self):
        assert _normalize_period("2023A") == "2023"

    def test_year_with_E_suffix(self):
        assert _normalize_period("2024E") == "2024"

    def test_none_returns_none(self):
        assert _normalize_period(None) is None

    def test_empty_returns_none(self):
        assert _normalize_period("") is None

    def test_quarterly_period_not_normalized(self):
        # Quarterly periods don't match 4-digit year pattern
        result = _normalize_period("Q1 2023")
        assert result is None or result == "Q1 2023"


# ── Metric normalization ───────────────────────────────────────────────────────

class TestNormalizeMetric:
    def test_revenue(self):
        assert _normalize_metric("Revenue") == "revenue"

    def test_revenues_plural(self):
        assert _normalize_metric("Revenues") == "revenue"

    def test_ebitda(self):
        assert _normalize_metric("EBITDA") == "ebitda"

    def test_net_income(self):
        assert _normalize_metric("Net Income") == "net_income"

    def test_eps(self):
        assert _normalize_metric("EPS") == "eps"

    def test_pe_ratio(self):
        assert _normalize_metric("P/E Ratio") == "pe_ratio"

    def test_ev_ebitda(self):
        assert _normalize_metric("EV/EBITDA") == "ev_ebitda"

    def test_unknown_returns_none(self):
        assert _normalize_metric("Total Assets") is None

    def test_case_insensitive(self):
        assert _normalize_metric("gross margin") == "gross_margin"
        assert _normalize_metric("GROSS MARGIN") == "gross_margin"


# ── Full table parsing via inline HTML ────────────────────────────────────────

def _write_html_report(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"<html><body>{content}</body></html>", encoding="utf-8")


class TestTableClaimsFromReport:
    def test_returns_empty_for_missing_file(self, tmp_path):
        result = table_claims_from_report(str(tmp_path / "nonexistent.html"), "NVDA")
        assert result == []

    def test_returns_empty_for_non_html_file(self, tmp_path):
        txt = tmp_path / "report.txt"
        txt.write_text("Revenue was $27B in 2023")
        result = table_claims_from_report(str(txt), "NVDA")
        assert result == []

    def test_parses_simple_revenue_table(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2022A</th><th>2023A</th></tr></thead>
          <tbody>
            <tr><td>Revenue</td><td>$16B</td><td>$27B</td></tr>
          </tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        assert len(claims) >= 1
        metrics = {c["metric"] for c in claims}
        assert "revenue" in metrics

    def test_claim_has_required_fields(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        if claims:
            c = claims[0]
            for field in ("claim_text", "claim_type", "metric", "unit",
                          "source_status", "confidence", "extraction_method", "ticker"):
                assert field in c, f"Missing field: {field}"

    def test_extraction_method_is_table_parser(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        if claims:
            assert all(c["extraction_method"] == "table_parser" for c in claims)

    def test_ticker_set_correctly(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "TSLA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "TSLA")
        if claims:
            assert all(c["ticker"] == "TSLA" for c in claims)

    def test_unknown_metrics_excluded(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody>
            <tr><td>Total Assets</td><td>$100B</td></tr>
            <tr><td>Revenue</td><td>$27B</td></tr>
          </tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        metrics = {c["metric"] for c in claims}
        assert "revenue" in metrics
        # "total_assets" is not in the metric map so should be absent
        assert all(c["metric"] != "total_assets" for c in claims)

    def test_deduplication_across_tables(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        # Should not have duplicate (revenue, 2023) pairs
        rev_2023 = [(c["metric"], c["period"]) for c in claims
                    if c["metric"] == "revenue" and c.get("period") == "2023"]
        assert len(rev_2023) <= 1

    def test_percent_values_get_percent_unit(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Gross Margin</td><td>75%</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        margin_claims = [c for c in claims if c["metric"] == "gross_margin"]
        if margin_claims:
            assert margin_claims[0]["unit"] == "percent"

    def test_period_normalized_to_4_digit_year(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        rev_claims = [c for c in claims if c["metric"] == "revenue"]
        if rev_claims:
            assert rev_claims[0].get("period") == "2023"

    def test_source_status_is_unverified(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        if claims:
            assert all(c["source_status"] == "unverified" for c in claims)

    def test_confidence_is_high(self, tmp_path):
        html = """
        <table>
          <thead><tr><th>Metric</th><th>2023A</th></tr></thead>
          <tbody><tr><td>Revenue</td><td>$27B</td></tr></tbody>
        </table>
        """
        path = tmp_path / "NVDA_report.html"
        _write_html_report(path, html)
        claims = table_claims_from_report(str(path), "NVDA")
        if claims:
            assert all(c["confidence"] == "high" for c in claims)
