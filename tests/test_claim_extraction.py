"""
Fixture-based unit tests for reliability_lab/claim_extraction.py.

No live API calls. All tests use local fixtures or inline strings.
Mark live tests with @pytest.mark.live and skip by default.
"""
import json
import sys
from pathlib import Path

import pytest

# Ensure the repo root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.claim_extraction import (
    _strip_html,
    _nearest_year,
    _normalize_value,
    _extract_regex,
    _load_prompt,
    _make_run_metadata,
)

REPO_ROOT = Path(__file__).parent.parent

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_HTML = FIXTURES / "sample_report_snippet.html"
SAMPLE_CLAIMS = FIXTURES / "sample_claims.json"


# ── _strip_html ───────────────────────────────────────────────────────────────

class TestStripHtml:
    def test_strips_script_tag(self):
        html = '<p>Hello</p><script>var x = 1;</script><p>World</p>'
        result = _strip_html(html)
        assert "var x" not in result
        assert "Hello" in result
        assert "World" in result

    def test_strips_style_tag(self):
        html = '<p>Text</p><style>body { color: red; }</style>'
        result = _strip_html(html)
        assert "color" not in result
        assert "Text" in result

    def test_preserves_table_text(self):
        html = '<table><tr><td>Revenue</td><td>27.0</td></tr></table>'
        result = _strip_html(html)
        assert "Revenue" in result
        assert "27.0" in result

    def test_sample_fixture(self):
        raw = SAMPLE_HTML.read_text()
        result = _strip_html(raw)
        assert "this should be stripped" not in result
        assert "sans-serif" not in result
        assert "Nvidia" in result
        assert "EBITDA" in result

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_plain_text_passthrough(self):
        text = "Revenue was $27 billion in FY2023."
        result = _strip_html(text)
        assert "Revenue" in result


# ── _nearest_year ─────────────────────────────────────────────────────────────

class TestNearestYear:
    def test_finds_year_before_match(self):
        text = "In 2023, revenue was $27 billion."
        # match position of "$27" ~ index 18
        pos = text.index("$27")
        year, is_est = _nearest_year(text, pos)
        assert year == "2023"
        assert is_est is False

    def test_finds_year_after_match(self):
        text = "Revenue of $60 billion in FY2024."
        pos = text.index("$60")
        year, is_est = _nearest_year(text, pos)
        assert year == "2024"

    def test_estimate_flag_on_e_suffix(self):
        text = "Revenue estimate $215 billion for 2025E."
        pos = text.index("$215")
        year, is_est = _nearest_year(text, pos)
        assert year == "2025"
        assert is_est is True

    def test_actual_suffix_not_estimate(self):
        # "A" suffix = Actual — must NOT be treated as forward estimate
        text = "Revenue $27 billion in 2023A."
        pos = text.index("$27")
        year, is_est = _nearest_year(text, pos)
        assert year == "2023"
        assert is_est is False

    def test_multi_year_sentence_attributes_correctly(self):
        # Verifies clause-boundary fix (P2-1): in compound sentences the " to " separator
        # is detected and each value is attributed to the year in its own clause.
        text = "Revenue grew from $27 billion in 2021 to $60 billion in 2022."
        pos_27 = text.index("$27")
        pos_60 = text.index("$60")
        year_27, _ = _nearest_year(text, pos_27)
        year_60, _ = _nearest_year(text, pos_60)
        assert year_27 == "2021"
        assert year_60 == "2022"

    def test_no_year_returns_none(self):
        text = "Revenue was strong this quarter."
        year, is_est = _nearest_year(text, 0)
        assert year is None

    def test_window_boundary(self):
        # Year more than 200 chars away should NOT be found
        text = "2020 " + " " * 205 + "$50 billion."
        pos = text.index("$50")
        year, _ = _nearest_year(text, pos, window=200)
        assert year is None


# ── _normalize_value ──────────────────────────────────────────────────────────

class TestNormalizeValue:
    def test_billion(self):
        assert _normalize_value("27", "B") == 27e9

    def test_billion_long(self):
        assert _normalize_value("60.9", "billion") == 60.9e9

    def test_million(self):
        assert _normalize_value("500", "M") == 500e6

    def test_trillion(self):
        assert _normalize_value("1.5", "T") == 1.5e12

    def test_trillion_long(self):
        assert _normalize_value("2", "trillion") == 2e12

    def test_comma_in_amount(self):
        assert _normalize_value("1,500", "M") == 1500e6

    def test_case_insensitive(self):
        assert _normalize_value("10", "BILLION") == 10e9


# ── _extract_regex ────────────────────────────────────────────────────────────

class TestExtractRegex:
    def _run_fixture(self):
        raw = SAMPLE_HTML.read_text()
        from reliability_lab.claim_extraction import _strip_html
        text = _strip_html(raw)
        return _extract_regex(text, "NVDA")

    def test_returns_list(self):
        claims = self._run_fixture()
        assert isinstance(claims, list)

    def test_at_least_one_claim(self):
        claims = self._run_fixture()
        assert len(claims) >= 1

    def test_all_claims_have_required_fields(self):
        claims = self._run_fixture()
        required = {"claim_text", "claim_type", "metric", "unit",
                    "source_status", "confidence", "extraction_method", "ticker"}
        for c in claims:
            missing = required - set(c.keys())
            assert not missing, f"Claim missing fields: {missing}"

    def test_ticker_is_set(self):
        claims = self._run_fixture()
        for c in claims:
            assert c["ticker"] == "NVDA"

    def test_extraction_method_is_regex(self):
        claims = self._run_fixture()
        for c in claims:
            assert c["extraction_method"] == "regex"

    def test_source_status_is_unverified(self):
        claims = self._run_fixture()
        for c in claims:
            assert c["source_status"] == "unverified"

    def test_ebitda_claim_extracted(self):
        claims = self._run_fixture()
        metrics = [c["metric"] for c in claims]
        assert "ebitda_margin" in metrics or "ebitda" in metrics, (
            f"No EBITDA claim found. Metrics found: {metrics}"
        )

    def test_pe_ratio_extracted_separately_from_ev_ebitda(self):
        # Verifies narrow-window distance fix (P2-2): "P/E of 37.7x and EV/EBITDA of 28.5x"
        # each gets the right metric label via distance comparison (not first-match wins).
        text = "The stock trades at a P/E of 37.7x and EV/EBITDA of 28.5x based on FY2025 estimates."
        claims = _extract_regex(text, "TEST")
        metrics = [c["metric"] for c in claims]
        assert "pe_ratio" in metrics, f"P/E not extracted. Metrics: {metrics}"
        assert "ev_ebitda" in metrics, f"EV/EBITDA not extracted. Metrics: {metrics}"

    def test_pe_ratio_claim_from_fixture(self):
        # End-to-end: the sample fixture has "P/E of 37.7x and EV/EBITDA of 28.5x";
        # after P2-2 fix both should be present in extracted claims.
        claims = self._run_fixture()
        metrics = [c["metric"] for c in claims]
        assert "ev_ebitda" in metrics, f"Expected ev_ebitda. Got: {metrics}"
        assert "pe_ratio" in metrics, f"Expected pe_ratio. Got: {metrics}"

    def test_no_duplicate_metric_period_value(self):
        claims = self._run_fixture()
        keys = [(c["metric"], c["period"], c.get("value_display", "")) for c in claims]
        assert len(keys) == len(set(keys)), "Duplicate (metric, period, value) found"

    def test_plain_text_revenue(self):
        text = "Revenue surged from $27 billion in FY2023 to $60.9 billion in FY2024."
        claims = _extract_regex(text, "NVDA")
        values = [c.get("value") for c in claims if c["metric"] == "revenue"]
        assert 27e9 in values or any(abs(v - 27e9) < 1e8 for v in values if v)

    def test_guidance_classification(self):
        text = "We expect revenue to reach $215 billion in 2025E."
        claims = _extract_regex(text, "TEST")
        assert any(c["claim_type"] == "guidance" for c in claims), (
            "Forward estimate should be classified as 'guidance'"
        )

    def test_empty_text_returns_empty_list(self):
        assert _extract_regex("", "NVDA") == []


# ── Fixture consistency ───────────────────────────────────────────────────────

class TestFixtureConsistency:
    """Verify the sample_claims.json fixture has expected structure."""

    def test_fixture_loads(self):
        data = json.loads(SAMPLE_CLAIMS.read_text())
        assert isinstance(data, list)
        assert len(data) == 5

    def test_all_have_ticker(self):
        data = json.loads(SAMPLE_CLAIMS.read_text())
        for c in data:
            assert c["ticker"] == "NVDA"

    def test_ebitda_claim_present(self):
        data = json.loads(SAMPLE_CLAIMS.read_text())
        assert any(c["metric"] == "ebitda_margin" for c in data)

    def test_guidance_claim_present(self):
        data = json.loads(SAMPLE_CLAIMS.read_text())
        assert any(c["claim_type"] == "guidance" for c in data)

    def test_pe_ratio_claim_present(self):
        data = json.loads(SAMPLE_CLAIMS.read_text())
        assert any(c["metric"] == "pe_ratio" for c in data)


# ── Prompt loading (P2-3) ─────────────────────────────────────────────────────

class TestPromptLoading:
    EXPECTED_PROMPTS = [
        "claim_extractor_v1",
        "skeptical_analyst_v1",
        "thesis_synthesizer_v1",
        "recommendation_extractor_v1",
        "quant_risk_reviewer_v1",
        "model_risk_reviewer_v1",
    ]

    def test_prompt_files_exist(self):
        for name in self.EXPECTED_PROMPTS:
            p = REPO_ROOT / "prompts" / f"{name}.txt"
            assert p.exists(), f"Missing prompt file: {p}"

    def test_load_prompt_returns_nonempty_string(self):
        text = _load_prompt("claim_extractor_v1")
        assert isinstance(text, str)
        assert len(text) > 50

    def test_load_prompt_missing_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            _load_prompt("nonexistent_prompt_xyz_abc")

    def test_skeptical_analyst_prompt_has_placeholders(self):
        text = _load_prompt("skeptical_analyst_v1")
        assert "{metrics_summary}" in text
        assert "{report_excerpt}" in text

    def test_synthesis_prompt_has_placeholders(self):
        text = _load_prompt("thesis_synthesizer_v1")
        assert "{ticker}" in text
        assert "{verified_facts}" in text


# ── Run metadata (P2-4) ───────────────────────────────────────────────────────

class TestRunMetadata:
    def _make(self, **kwargs):
        defaults = dict(
            ticker="NVDA",
            phase="claim_extraction",
            model_name="claude-sonnet-4-6",
            provider="anthropic",
            temperature=0,
            prompt_file="claim_extractor_v1.txt",
            prompt_text="test prompt template",
            input_text="test input text",
            output_text='[{"metric": "revenue"}]',
            claims_extracted=1,
        )
        defaults.update(kwargs)
        return _make_run_metadata(**defaults)

    def test_required_fields_present(self):
        meta = self._make()
        for field in ["run_id", "timestamp", "ticker", "phase", "model_name",
                      "provider", "temperature", "prompt_hash", "input_hash",
                      "output_hash", "fallback_used"]:
            assert field in meta, f"Missing field: {field}"

    def test_run_id_is_uuid(self):
        import uuid
        meta = self._make()
        uuid.UUID(meta["run_id"])  # raises ValueError if not valid UUID

    def test_hashes_are_sha256_prefixed(self):
        meta = self._make()
        assert meta["prompt_hash"].startswith("sha256:")
        assert meta["input_hash"].startswith("sha256:")
        assert meta["output_hash"].startswith("sha256:")

    def test_prompt_version_extracted_from_filename(self):
        meta = self._make(prompt_file="claim_extractor_v1.txt")
        assert meta["prompt_version"] == "1"

    def test_fallback_used_false_for_anthropic(self):
        meta = self._make(provider="anthropic")
        assert meta["fallback_used"] is False

    def test_fallback_used_true_for_ollama(self):
        meta = self._make(provider="ollama_fallback")
        assert meta["fallback_used"] is True

    def test_claims_extracted_recorded(self):
        meta = self._make(claims_extracted=7)
        assert meta["claims_extracted"] == 7
