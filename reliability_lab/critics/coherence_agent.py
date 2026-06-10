"""
Coherence Agent — G2 specialist agent.

Assesses whether the report's recommendation, thesis, and data quality
are internally consistent. Detects: BUY with high ICR, thesis vs. data mismatch,
overconfident forward projections, miscalibrated confidence.

Output: output/{TICKER}/{TICKER}_coherence_analysis.json
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call


def _extract_recommendation(output_dir_path: Path, ticker: str) -> str:
    """Read recommendation from {TICKER}_recommendation.json if available."""
    rec_path = output_dir_path / f"{ticker}_recommendation.json"
    if rec_path.exists():
        try:
            d = json.loads(rec_path.read_text())
            signal = d.get("signal", d.get("recommendation", "N/A"))
            return str(signal)
        except Exception:
            pass
    return "N/A"


def _extract_verdicts(output_dir_path: Path, ticker: str) -> dict:
    """Read verdicts from existing critic outputs."""
    verdicts = {
        "quant_risk_verdict": "N/A",
        "model_risk_verdict": "N/A",
        "earnings_quality_verdict": "N/A",
        "valuation_verdict": "N/A",
    }
    mappings = {
        "quant_risk_verdict": f"{ticker}_quant_risk_review.json",
        "model_risk_verdict": f"{ticker}_model_risk_review.json",
        "earnings_quality_verdict": f"{ticker}_earnings_analysis.json",
        "valuation_verdict": f"{ticker}_valuation_analysis.json",
    }
    for key, filename in mappings.items():
        path = output_dir_path / filename
        if path.exists():
            try:
                d = json.loads(path.read_text())
                verdicts[key] = d.get(key, "N/A")
            except Exception:
                pass
    return verdicts


def run_coherence_analysis(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    gate: Optional[dict] = None,
) -> Optional[dict]:
    """
    Run the Coherence Agent.
    Returns the parsed analysis dict, or None if no LLM available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    icr = m.get("incorrect_claim_rate", "N/A")
    scr = m.get("source_coverage_rate", "N/A")
    scorecard_summary = (
        f"  Total claims: {s.get('total_claims', 0)} | "
        f"Verified: {s.get('verified_count', 0)} | "
        f"Incorrect: {s.get('incorrect_count', 0)} | "
        f"SCR: {scr} | ICR: {icr} | "
        f"VD: {m.get('valuation_dispersion', 'N/A')}"
    )

    recommendation = _extract_recommendation(out_dir, ticker)
    verdicts = _extract_verdicts(out_dir, ticker)
    gate_decision = gate.get("decision", "N/A") if gate else "N/A"

    try:
        tmpl = _load_prompt("coherence_agent_v1")
    except FileNotFoundError:
        print(f"[{ticker}] coherence_agent: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{ticker}", ticker)
        .replace("{recommendation}", recommendation)
        .replace("{icr}", str(icr))
        .replace("{scr}", str(scr))
        .replace("{gate_decision}", gate_decision)
        .replace("{scorecard_summary}", scorecard_summary)
        .replace("{quant_risk_verdict}", verdicts["quant_risk_verdict"])
        .replace("{model_risk_verdict}", verdicts["model_risk_verdict"])
        .replace("{earnings_quality_verdict}", verdicts["earnings_quality_verdict"])
        .replace("{valuation_verdict}", verdicts["valuation_verdict"])
    )

    print(f"[{ticker}] Running Coherence Agent...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=1024)
    if not raw:
        print(f"[{ticker}] Coherence Agent: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="coherence_agent",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="coherence_agent_v1.txt",
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
            result = {
                "signal_reliability": "unknown",
                "coherence_rationale": raw[:500],
            }
    else:
        result = {
            "signal_reliability": "unknown",
            "coherence_rationale": raw[:500],
        }

    result["_computed"] = {
        "recommendation": recommendation,
        "gate_decision": gate_decision,
        "icr": icr,
        "scr": scr,
        "specialist_verdicts": verdicts,
    }

    out_path = out_dir / f"{ticker}_coherence_analysis.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[{ticker}] Coherence analysis → {out_path.name}")
    return result
