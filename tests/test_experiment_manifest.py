"""
Tests for reliability_lab/backtesting/experiment_manifest.py.

Schema validation + builder correctness. No live API calls.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.backtesting.experiment_manifest import build_manifest, save_manifest

try:
    from jsonschema.validators import Draft202012Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "experiment_manifest.schema.json"


def _validate(instance, schema):
    Draft202012Validator(schema).validate(instance)


# ── Builder correctness ────────────────────────────────────────────────────────

class TestBuildManifest:
    def test_required_fields_present(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction", "fact_verification"])
        for field in ("experiment_id", "created_at", "tickers", "phases"):
            assert field in m, f"Missing required field: {field}"

    def test_ticker_in_tickers_list(self):
        m = build_manifest("TSLA", "auto", ["claim_extraction"])
        assert "TSLA" in m["tickers"]

    def test_mode_stored_as_extraction_mode(self):
        m = build_manifest("NVDA", "llm", ["claim_extraction"])
        assert m["extraction_mode"] == "llm"

    def test_phases_preserved(self):
        phases = ["claim_extraction", "fact_verification", "adversarial_critic"]
        m = build_manifest("NVDA", "auto", phases)
        assert m["phases"] == phases

    def test_experiment_id_contains_ticker(self):
        m = build_manifest("META", "regex", ["claim_extraction"])
        assert "meta" in m["experiment_id"].lower()

    def test_experiment_id_contains_mode(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        assert "regex" in m["experiment_id"]

    def test_created_at_is_iso_format(self):
        from datetime import datetime
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        datetime.fromisoformat(m["created_at"])

    def test_optional_fields_default_correctly(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        assert m["description"] is None
        assert m["cutoff_dates"] == []
        assert m["model_name"] is None
        assert m["provider"] is None
        assert m["prompt_versions"] == {}
        assert m["data_sources"] == []
        assert m["outputs"] == []
        assert m["fallback_used"] is False
        assert m["known_limitations"] == []

    def test_optional_fields_passed_through(self):
        m = build_manifest(
            "NVDA", "auto", ["claim_extraction"],
            description="Test run",
            model_name="claude-sonnet-4-6",
            provider="anthropic",
            prompt_versions={"claim_extraction": "v1"},
            outputs=["output/NVDA/claims.json"],
            fallback_used=True,
            known_limitations=["sample_n_small"],
        )
        assert m["description"] == "Test run"
        assert m["model_name"] == "claude-sonnet-4-6"
        assert m["provider"] == "anthropic"
        assert m["prompt_versions"] == {"claim_extraction": "v1"}
        assert "output/NVDA/claims.json" in m["outputs"]
        assert m["fallback_used"] is True
        assert "sample_n_small" in m["known_limitations"]

    def test_git_sha_is_string_or_none(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        assert m["git_sha"] is None or isinstance(m["git_sha"], str)


# ── Schema validation ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
class TestManifestSchemaValidation:
    SCHEMA = json.loads(SCHEMA_PATH.read_text()) if SCHEMA_PATH.exists() else {}

    def test_basic_manifest_passes_schema(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction", "fact_verification"])
        _validate(m, self.SCHEMA)

    def test_full_manifest_passes_schema(self):
        m = build_manifest(
            "TSLA", "auto", ["claim_extraction", "fact_verification", "adversarial_critic"],
            description="Full audit run",
            cutoff_dates=["2025-06-01"],
            model_name="claude-sonnet-4-6",
            provider="anthropic",
            prompt_versions={"claim_extraction": "claim_extractor_v1"},
            data_sources=[
                {"source_name": "SEC EDGAR XBRL", "tier": 1, "cache_hit": True},
                {"source_name": "FMP free tier",  "tier": 3, "cache_hit": True},
            ],
            outputs=["output/TSLA/TSLA_claims.json"],
            fallback_used=False,
            known_limitations=["sample_n_equals_1"],
        )
        _validate(m, self.SCHEMA)

    def test_invalid_phase_fails_schema(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        m["phases"].append("invalid_phase")
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_invalid_mode_fails_schema(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        m["extraction_mode"] = "unknown_mode"
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)

    def test_missing_tickers_fails_schema(self):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        m["tickers"] = []
        with pytest.raises(Exception):
            _validate(m, self.SCHEMA)


# ── Save function ──────────────────────────────────────────────────────────────

class TestSaveManifest:
    def test_save_creates_file(self, tmp_path):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        path = save_manifest(m, str(tmp_path), "NVDA")
        assert path.exists()

    def test_save_filename_convention(self, tmp_path):
        m = build_manifest("TSLA", "regex", ["claim_extraction"])
        path = save_manifest(m, str(tmp_path), "TSLA")
        assert path.name == "TSLA_experiment_manifest.json"

    def test_saved_json_is_valid(self, tmp_path):
        m = build_manifest("NVDA", "regex", ["claim_extraction"])
        path = save_manifest(m, str(tmp_path), "NVDA")
        loaded = json.loads(path.read_text())
        assert loaded["tickers"] == ["NVDA"]
