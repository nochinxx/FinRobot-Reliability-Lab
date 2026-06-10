"""
Earnings Analyst — G2 specialist agent.

Evaluates the accuracy and internal consistency of earnings-related claims:
  - Revenue claim accuracy vs. SEC EDGAR (historical)
  - EPS accuracy vs. FMP
  - Margin claim internal consistency
  - Forward projection qualification check

Output: output/{TICKER}/{TICKER}_earnings_analysis.json
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call

_EARNINGS_METRICS = {"revenue", "eps", "ebitda", "gross_margin", "net_margin",
                     "ebitda_margin", "revenue_growth", "net_income", "free_cash_flow"}


def _format_earnings_rows(fact_rows: list[dict]) -> str:
    """Format earnings-related fact rows for the prompt."""
    rows = [r for r in fact_rows if r.get("metric", "") in _EARNINGS_METRICS]
    if not rows:
        return "  (no earnings-related claims verified in this run)"
    lines = []
    for r in rows:
        status = r.get("verification_status", "unsupported")
        period = r.get("period", "")
        metric = r.get("metric", "")
        claimed = r.get("claimed_value", "")
        verified = r.get("verified_value", "")
        source = r.get("source", "")
        flag = "❌" if status == "incorrect" else ("✅" if status == "verified" else "○")
        if verified:
            lines.append(f"  {flag} {metric} ({period}): claimed={claimed}, verified={verified} [{source}]")
        else:
            lines.append(f"  {flag} {metric} ({period}): claimed={claimed}, status={status}")
    return "\n".join(lines) or "  (no earnings rows)"


def run_earnings_analysis(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
) -> Optional[dict]:
    """
    Run the Earnings Analyst agent.
    Returns the parsed analysis dict, or None if no LLM available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    earnings_rows = _format_earnings_rows(fact_rows)
    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    scorecard_summary = (
        f"  Total claims: {s.get('total_claims', 0)} | "
        f"Verified: {s.get('verified_count', 0)} | "
        f"Incorrect: {s.get('incorrect_count', 0)} | "
        f"SCR: {m.get('source_coverage_rate', 'N/A')} | "
        f"ICR: {m.get('incorrect_claim_rate', 'N/A')}"
    )

    try:
        tmpl = _load_prompt("earnings_analyst_v1")
    except FileNotFoundError:
        print(f"[{ticker}] earnings_analyst: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{ticker}", ticker)
        .replace("{earnings_rows}", earnings_rows)
        .replace("{scorecard_summary}", scorecard_summary)
    )

    print(f"[{ticker}] Running Earnings Analyst...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=1024)
    if not raw:
        print(f"[{ticker}] Earnings Analyst: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="earnings_analyst",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="earnings_analyst_v1.txt",
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
                "earnings_quality_verdict": "unknown",
                "earnings_quality_rationale": raw[:500],
            }
    else:
        result = {
            "earnings_quality_verdict": "unknown",
            "earnings_quality_rationale": raw[:500],
        }

    # Inject computed stats
    earnings_fact_rows = [r for r in fact_rows if r.get("metric", "") in _EARNINGS_METRICS]
    n_incorrect = sum(1 for r in earnings_fact_rows if r.get("verification_status") == "incorrect")
    n_verified = sum(1 for r in earnings_fact_rows if r.get("verification_status") == "verified")
    result["_computed"] = {
        "earnings_claims_total": len(earnings_fact_rows),
        "earnings_verified": n_verified,
        "earnings_incorrect": n_incorrect,
        "earnings_icr": round(n_incorrect / len(earnings_fact_rows), 3) if earnings_fact_rows else 0.0,
    }

    out_path = out_dir / f"{ticker}_earnings_analysis.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[{ticker}] Earnings analysis → {out_path.name}")
    return result
