"""
Schema validation tests for all data-contract fixtures.

Validates each fixture file against its JSON Schema using jsonschema Draft202012Validator.
No live API calls. All tests use local fixture and schema files.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

try:
    from jsonschema import ValidationError
    from jsonschema.validators import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

pytestmark = pytest.mark.skipif(
    not HAS_JSONSCHEMA,
    reason="jsonschema not installed — run: pip install jsonschema"
)

REPO = Path(__file__).parent.parent
SCHEMAS = REPO / "schemas"
FIXTURES = Path(__file__).parent / "fixtures"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text())


def _validate(instance, schema):
    """Raise jsonschema.ValidationError if invalid."""
    validator = Draft202012Validator(schema)
    validator.validate(instance)


# ── sample_claims.json → claim.schema.json ────────────────────────────────────

class TestClaimSchema:
    SCHEMA = _load_schema("claim.schema.json") if HAS_JSONSCHEMA else {}

    def test_all_fixture_claims_valid(self):
        claims = json.loads((FIXTURES / "sample_claims.json").read_text())
        for i, claim in enumerate(claims):
            try:
                _validate(claim, self.SCHEMA)
            except Exception as e:
                pytest.fail(f"Claim[{i}] failed validation: {e}")

    def test_rejects_missing_required_field(self):
        bad = {
            "claim_text": "Revenue was $27B in 2023.",
            "claim_type": "financial",
            "metric": "revenue",
            # missing: unit, source_status, confidence, extraction_method, ticker
        }
        with pytest.raises(Exception):
            _validate(bad, self.SCHEMA)

    def test_rejects_unknown_claim_type(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["claim_type"] = "made_up_type"
        with pytest.raises(Exception):
            _validate(good, self.SCHEMA)

    def test_rejects_unknown_metric(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["metric"] = "not_a_real_metric"
        with pytest.raises(Exception):
            _validate(good, self.SCHEMA)

    def test_rejects_additional_properties(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["unexpected_field"] = "should_fail"
        with pytest.raises(Exception):
            _validate(good, self.SCHEMA)

    def test_rejects_invalid_ticker_format(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["ticker"] = "nvda"  # lowercase — pattern requires uppercase
        with pytest.raises(Exception):
            _validate(good, self.SCHEMA)

    def test_rejects_invalid_prompt_hash_format(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["prompt_hash"] = "not-a-sha256-hash"
        with pytest.raises(Exception):
            _validate(good, self.SCHEMA)

    def test_valid_prompt_hash_accepted(self):
        good = json.loads((FIXTURES / "sample_claims.json").read_text())[0].copy()
        good["prompt_hash"] = "sha256:" + "a" * 64
        _validate(good, self.SCHEMA)  # should not raise


# ── sample_fact_table.csv → fact_row.schema.json ──────────────────────────────

class TestFactRowSchema:
    SCHEMA = _load_schema("fact_row.schema.json") if HAS_JSONSCHEMA else {}

    def _load_rows(self):
        rows = []
        with open(FIXTURES / "sample_fact_table.csv", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
        return rows

    def test_all_fixture_rows_valid(self):
        rows = self._load_rows()
        for i, row in enumerate(rows):
            try:
                _validate(row, self.SCHEMA)
            except Exception as e:
                pytest.fail(f"Row[{i}] ({row.get('metric')}) failed validation: {e}")

    def test_rejects_invalid_verification_status(self):
        row = self._load_rows()[0].copy()
        row["verification_status"] = "maybe_correct"
        with pytest.raises(Exception):
            _validate(row, self.SCHEMA)

    def test_rejects_missing_ticker(self):
        row = self._load_rows()[0].copy()
        del row["ticker"]
        with pytest.raises(Exception):
            _validate(row, self.SCHEMA)

    def test_rejects_additional_column(self):
        row = self._load_rows()[0].copy()
        row["extra_column"] = "not allowed"
        with pytest.raises(Exception):
            _validate(row, self.SCHEMA)

    def test_source_conflict_status_accepted(self):
        row = self._load_rows()[0].copy()
        row["verification_status"] = "SOURCE_CONFLICT"
        _validate(row, self.SCHEMA)  # planned status must be accepted by schema


# ── sample_scorecard.json → reliability_scorecard.schema.json ─────────────────

class TestScorecardSchema:
    SCHEMA = _load_schema("reliability_scorecard.schema.json") if HAS_JSONSCHEMA else {}

    def test_fixture_valid(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        _validate(sc, self.SCHEMA)

    def test_rejects_missing_summary(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        del sc["summary"]
        with pytest.raises(Exception):
            _validate(sc, self.SCHEMA)

    def test_rejects_negative_count(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        sc["summary"]["verified_count"] = -1
        with pytest.raises(Exception):
            _validate(sc, self.SCHEMA)

    def test_rejects_rate_above_one(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        sc["metrics"]["source_coverage_rate"] = 1.5
        with pytest.raises(Exception):
            _validate(sc, self.SCHEMA)

    def test_null_valuation_dispersion_accepted(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        sc["metrics"]["valuation_dispersion"] = None
        _validate(sc, self.SCHEMA)

    def test_rejects_additional_properties_in_summary(self):
        sc = json.loads((FIXTURES / "sample_scorecard.json").read_text())
        sc["summary"]["extra"] = 99
        with pytest.raises(Exception):
            _validate(sc, self.SCHEMA)


# ── run_metadata.schema.json — structural and constraint tests ────────────────

class TestRunMetadataSchema:
    SCHEMA = _load_schema("run_metadata.schema.json") if HAS_JSONSCHEMA else {}

    def _minimal(self):
        return {
            "run_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-06-08T12:00:00Z",
            "ticker": "NVDA",
            "phase": "claim_extraction",
            "model_name": "claude-sonnet-4-6",
            "provider": "anthropic",
        }

    def test_minimal_valid_object(self):
        _validate(self._minimal(), self.SCHEMA)

    def test_rejects_missing_required_field(self):
        m = self._minimal()
        del m["phase"]
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_rejects_unknown_phase(self):
        m = self._minimal()
        m["phase"] = "not_a_real_phase"
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_rejects_unknown_provider(self):
        m = self._minimal()
        m["provider"] = "openai"
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_rejects_temperature_above_two(self):
        m = self._minimal()
        m["temperature"] = 2.5
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_temperature_zero_accepted(self):
        m = self._minimal()
        m["temperature"] = 0.0
        _validate(m, self.SCHEMA)

    def test_rejects_malformed_prompt_hash(self):
        m = self._minimal()
        m["prompt_hash"] = "abc123"  # not sha256:... format
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_valid_sha256_hash_accepted(self):
        m = self._minimal()
        m["prompt_hash"] = "sha256:" + "b" * 64
        _validate(m, self.SCHEMA)

    def test_rejects_invalid_ticker_format(self):
        m = self._minimal()
        m["ticker"] = "nvda"
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_all_phases_accepted(self):
        phases = [
            "claim_extraction", "fact_verification", "adversarial_critic",
            "skeptical_analyst", "thesis_synthesizer", "recommendation_extraction",
            "backtest", "quant_risk_review", "model_risk_review",
        ]
        for phase in phases:
            m = self._minimal()
            m["phase"] = phase
            _validate(m, self.SCHEMA)

    def test_ollama_fallback_provider_accepted(self):
        m = self._minimal()
        m["provider"] = "ollama_fallback"
        _validate(m, self.SCHEMA)

    def test_none_provider_accepted(self):
        m = self._minimal()
        m["provider"] = "none"
        _validate(m, self.SCHEMA)

    def test_rejects_additional_properties(self):
        m = self._minimal()
        m["unknown_field"] = "oops"
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_make_run_metadata_produces_valid_instance(self):
        """run_metadata dicts produced at runtime validate against the schema."""
        import sys
        sys.path.insert(0, str(REPO / ".."))
        from reliability_lab.claim_extraction import _make_run_metadata
        meta = _make_run_metadata(
            ticker="NVDA",
            phase="claim_extraction",
            model_name="claude-sonnet-4-6",
            provider="anthropic",
            temperature=0,
            prompt_file="claim_extractor_v1.txt",
            prompt_text="test prompt",
            input_text="test input",
            output_text="[]",
            claims_extracted=0,
        )
        _validate(meta, self.SCHEMA)
