"""
Quant Risk Reviewer — Phase 5b.

Assesses the quantitative reliability of one audit run:
  - ICR artifact vs. true-error distinction
  - Coverage gaps by metric type
  - Valuation dispersion consistency
  - Source-tier breakdown
  - Quant risk verdict: low / medium / high

Output: output/{TICKER}/{TICKER}_quant_risk_review.json
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call


def _format_scorecard_summary(scorecard: dict) -> str:
    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    t = scorecard.get("thresholds", {})
    lines = [
        f"  Total claims:            {s.get('total_claims', 0)}",
        f"  Machine-verifiable:      {s.get('machine_verifiable_claims', 0)}",
        f"  Verified:                {s.get('verified_count', 0)}",
        f"  Incorrect:               {s.get('incorrect_count', 0)}",
        f"  Source coverage rate:    {m.get('source_coverage_rate', 'N/A')}"
        f"  (target ≥0.80: {'PASS' if t.get('source_coverage_rate', {}).get('pass') else 'FAIL'})",
        f"  Primary source coverage: {m.get('primary_source_coverage_rate', 'N/A')}",
        f"  Incorrect claim rate:    {m.get('incorrect_claim_rate', 'N/A')}"
        f"  (target ≤0.05: {'PASS' if t.get('incorrect_claim_rate', {}).get('pass') else 'FAIL'})",
        f"  Unsupported claim rate:  {m.get('unsupported_claim_rate', 'N/A')}",
    ]
    return "\n".join(lines)


def _format_by_metric(scorecard: dict) -> str:
    bm = scorecard.get("by_metric", {})
    if not bm:
        return "  (no per-metric breakdown available)"
    lines = []
    for metric, counts in sorted(bm.items()):
        lines.append(
            f"  {metric}: total={counts.get('total',0)}, "
            f"verified={counts.get('verified',0)}, "
            f"incorrect={counts.get('incorrect',0)}, "
            f"nmv={counts.get('not_machine_verifiable',0)}"
        )
    return "\n".join(lines)


def _compute_source_tier_breakdown(fact_rows: list[dict]) -> dict:
    tier1 = sum(1 for r in fact_rows if str(r.get("source_tier","")).strip() == "1"
                and r.get("verification_status") in ("verified","incorrect","SOURCE_CONFLICT"))
    tier3 = sum(1 for r in fact_rows if str(r.get("source_tier","")).strip() == "3"
                and r.get("verification_status") in ("verified","incorrect","SOURCE_CONFLICT"))
    total = tier1 + tier3
    return {
        "tier_1_fraction": round(tier1 / total, 3) if total else 0.0,
        "tier_3_fraction": round(tier3 / total, 3) if total else 0.0,
    }


def run_quant_risk_review(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    signal: str = "N/A",
    signal_rationale: str = "N/A",
) -> Optional[dict]:
    """
    Run the Quant Risk Reviewer LLM agent.
    Returns the parsed review dict, or None if no LLM is available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    vd = scorecard.get("metrics", {}).get("valuation_dispersion")
    vd_str = f"{vd:.3f}" if vd is not None else "N/A"

    scorecard_summary = _format_scorecard_summary(scorecard)
    by_metric_str     = _format_by_metric(scorecard)

    try:
        tmpl = _load_prompt("quant_risk_reviewer_v1")
    except FileNotFoundError:
        print(f"[{ticker}] quant_risk_reviewer: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{ticker}", ticker)
        .replace("{scorecard_summary}", scorecard_summary)
        .replace("{by_metric}", by_metric_str)
        .replace("{valuation_dispersion}", vd_str)
        .replace("{signal}", signal)
        .replace("{signal_rationale}", signal_rationale)
    )

    print(f"[{ticker}] Running Quant Risk Reviewer...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=1024)
    if not raw:
        print(f"[{ticker}] Quant Risk Reviewer: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="quant_risk_reviewer",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="quant_risk_reviewer_v1.txt",
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

    # Fill source_tier_breakdown from fact_rows if LLM left it empty
    if "source_tier_breakdown" not in result or not result.get("source_tier_breakdown"):
        result["source_tier_breakdown"] = _compute_source_tier_breakdown(fact_rows)

    out_path = out_dir / f"{ticker}_quant_risk_review.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[{ticker}] Quant risk verdict: {result.get('quant_risk_verdict','N/A')} → {out_path}")
    return result
