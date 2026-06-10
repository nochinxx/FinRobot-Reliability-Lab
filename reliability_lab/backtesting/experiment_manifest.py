"""
Experiment manifest builder.

Records full reproducibility context for a batch audit or backtest run.
Output: output/{TICKER}/{TICKER}_experiment_manifest.json
Schema:  schemas/experiment_manifest.schema.json
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _git_sha() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def build_manifest(
    ticker: str,
    mode: str,
    phases: list[str],
    *,
    description: Optional[str] = None,
    cutoff_dates: Optional[list[str]] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    prompt_versions: Optional[dict] = None,
    data_sources: Optional[list[dict]] = None,
    outputs: Optional[list[str]] = None,
    fallback_used: bool = False,
    known_limitations: Optional[list[str]] = None,
) -> dict:
    """
    Build an experiment manifest dict matching experiment_manifest.schema.json.

    phases: list of phase names from schema enum:
      claim_extraction, fact_verification, adversarial_critic,
      backtest, quant_risk_review, model_risk_review
    """
    ts = datetime.now(timezone.utc)
    experiment_id = f"{ticker.lower()}-{ts.strftime('%Y%m%d-%H%M%S')}-{mode}"

    return {
        "experiment_id":   experiment_id,
        "created_at":      ts.isoformat(),
        "description":     description,
        "tickers":         [ticker],
        "cutoff_dates":    cutoff_dates or [],
        "phases":          phases,
        "extraction_mode": mode,
        "model_name":      model_name,
        "provider":        provider,
        "prompt_versions": prompt_versions or {},
        "data_sources":    data_sources or [],
        "outputs":         outputs or [],
        "fallback_used":   fallback_used,
        "known_limitations": known_limitations or [],
        "git_sha":         _git_sha(),
    }


def save_manifest(manifest: dict, output_dir: str, ticker: str) -> Path:
    out = Path(output_dir) / f"{ticker}_experiment_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    return out
