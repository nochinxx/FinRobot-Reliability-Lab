"""
Model Risk Reviewer — Phase 5c.

Assesses pipeline-level model risk for institutional deployment:
  - Determinism risk (temperature, provider, fallback)
  - Input sensitivity (extraction window, heuristics)
  - Coverage gap risk (low SCR)
  - Prompt fragility
  - Model risk verdict: not-ready / prototype / conditional-production / production-ready

Output: output/{TICKER}/{TICKER}_model_risk_review.json
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call


def _load_run_metadata_entries(output_dir: str, ticker: str) -> list[dict]:
    """Load the run_metadata.jsonl entries for this ticker's run, if they exist."""
    meta_path = Path(output_dir) / f"{ticker}_run_metadata.jsonl"
    entries = []
    if meta_path.exists():
        for line in meta_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _extract_pipeline_metadata(run_meta: list[dict], scorecard: dict) -> dict:
    """Extract key pipeline provenance fields from run metadata entries."""
    extractor_entry = next(
        (e for e in run_meta if e.get("phase") == "claim_extraction"), {}
    )
    critic_entry = next(
        (e for e in run_meta if e.get("phase") == "skeptical_analyst"), {}
    )
    return {
        "extractor_model":       extractor_entry.get("model_name", "unknown"),
        "extractor_provider":    extractor_entry.get("provider", "unknown"),
        "claim_prompt_version":  extractor_entry.get("prompt_version", "claim_extractor_v1"),
        "critic_model":          critic_entry.get("model_name", "N/A"),
        "critic_provider":       critic_entry.get("provider", "N/A"),
        "critic_prompt_version": critic_entry.get("prompt_version", "N/A"),
        "fallback_used":         any(e.get("fallback_used") for e in run_meta),
        "total_claims":          scorecard.get("summary", {}).get("total_claims", 0),
        "machine_verifiable":    scorecard.get("summary", {}).get("machine_verifiable_claims", 0),
        "verified_count":        scorecard.get("summary", {}).get("verified_count", 0),
        "incorrect_count":       scorecard.get("summary", {}).get("incorrect_count", 0),
        "icr":                   scorecard.get("metrics", {}).get("incorrect_claim_rate", "N/A"),
        "scr":                   scorecard.get("metrics", {}).get("source_coverage_rate", "N/A"),
    }


def run_model_risk_review(
    ticker: str,
    scorecard: dict,
    output_dir: str,
    report_generator: str = "FinRobot (Gemma4 12B MLX via Ollama)",
) -> Optional[dict]:
    """
    Run the Model Risk Reviewer LLM agent.
    Loads run_metadata.jsonl from output_dir to populate pipeline provenance.
    Returns the parsed review dict, or None if no LLM is available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_meta = _load_run_metadata_entries(output_dir, ticker)
    pm = _extract_pipeline_metadata(run_meta, scorecard)

    try:
        tmpl = _load_prompt("model_risk_reviewer_v1")
    except FileNotFoundError:
        print(f"[{ticker}] model_risk_reviewer: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{ticker}", ticker)
        .replace("{report_generator}", report_generator)
        .replace("{extractor_model}", str(pm["extractor_model"]))
        .replace("{extractor_provider}", str(pm["extractor_provider"]))
        .replace("{critic_model}", str(pm["critic_model"]))
        .replace("{critic_provider}", str(pm["critic_provider"]))
        .replace("{fallback_used}", str(pm["fallback_used"]))
        .replace("{claim_prompt_version}", str(pm["claim_prompt_version"]))
        .replace("{critic_prompt_version}", str(pm["critic_prompt_version"]))
        .replace("{total_claims}", str(pm["total_claims"]))
        .replace("{machine_verifiable}", str(pm["machine_verifiable"]))
        .replace("{verified_count}", str(pm["verified_count"]))
        .replace("{incorrect_count}", str(pm["incorrect_count"]))
        .replace("{icr}", str(pm["icr"]))
        .replace("{scr}", str(pm["scr"]))
    )

    print(f"[{ticker}] Running Model Risk Reviewer...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=1024)
    if not raw:
        print(f"[{ticker}] Model Risk Reviewer: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="model_risk_reviewer",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="model_risk_reviewer_v1.txt",
            prompt_text=tmpl,
            input_text=prompt,
            output_text=raw,
        ),
        out_dir,
    )

    start = raw.find("{"); end = raw.rfind("}") + 1
    result: dict = {}
    if start != -1 and end > start:
        try:
            result = json.loads(raw[start:end])
        except json.JSONDecodeError:
            result = {"raw_response": raw, "parse_error": True}
    else:
        result = {"raw_response": raw, "parse_error": True}

    result["ticker"] = ticker

    out_path = out_dir / f"{ticker}_model_risk_review.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[{ticker}] Model risk verdict: {result.get('model_risk_verdict','N/A')} → {out_path}")
    return result
