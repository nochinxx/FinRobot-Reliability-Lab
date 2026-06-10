"""
Multi-Agent Synthesizer — G2 orchestrator.

Runs the full specialist agent panel (Earnings Analyst, Valuation Agent, Coherence Agent)
and aggregates their outputs into a structured multi_agent_review.json.

Designed as a drop-in addition to the --critic pipeline.
Usage: run_reliability_audit.py --agents
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from reliability_lab.critics.earnings_analyst import run_earnings_analysis
from reliability_lab.critics.valuation_agent import run_valuation_analysis
from reliability_lab.critics.coherence_agent import run_coherence_analysis

_VERDICT_ORDER = {
    "high": 3, "medium": 2, "low": 1,        # quant/earnings verdicts (high = bad)
    "unreliable": 3, "questionable": 2, "sound": 1,  # valuation
    "unreliable_r": 3, "conditional": 2, "reliable": 1,  # coherence (signal reliability)
    "unknown": 0,
}


def _aggregate_verdicts(
    earnings: Optional[dict],
    valuation: Optional[dict],
    coherence: Optional[dict],
) -> dict:
    """Compute an overall panel verdict from specialist results."""
    verdicts = {}
    if earnings:
        verdicts["earnings"] = earnings.get("earnings_quality_verdict", "unknown")
    if valuation:
        verdicts["valuation"] = valuation.get("valuation_verdict", "unknown")
    if coherence:
        verdicts["coherence"] = coherence.get("signal_reliability", "unknown")

    scores = [_VERDICT_ORDER.get(v, 0) for v in verdicts.values()]
    max_score = max(scores, default=0)

    if max_score >= 3:
        panel_verdict = "CONCERN"
    elif max_score >= 2:
        panel_verdict = "REVIEW"
    else:
        panel_verdict = "ACCEPTABLE"

    return {
        "specialist_verdicts": verdicts,
        "panel_verdict": panel_verdict,
        "panel_verdict_explanation": {
            "CONCERN": "One or more specialist agents identified serious reliability concerns. "
                       "Do not use this report for investment decisions without human review.",
            "REVIEW": "Moderate concerns identified. The report may be usable but requires "
                      "analyst review of the flagged items.",
            "ACCEPTABLE": "No major concerns identified. Routine human oversight recommended.",
        }.get(panel_verdict, ""),
    }


def run_multi_agent_review(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    gate: Optional[dict] = None,
) -> dict:
    """
    Run the full G2 specialist agent panel and produce multi_agent_review.json.
    Agents that fail (no LLM) are skipped gracefully.
    Returns the aggregated review dict.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[{ticker}] ─── Multi-Agent Review Panel ───")

    earnings = run_earnings_analysis(ticker, scorecard, fact_rows, output_dir)
    valuation = run_valuation_analysis(ticker, scorecard, fact_rows, output_dir)
    coherence = run_coherence_analysis(ticker, scorecard, fact_rows, output_dir, gate)

    aggregated = _aggregate_verdicts(earnings, valuation, coherence)

    review = {
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_run": [
            k for k, v in [
                ("earnings_analyst", earnings),
                ("valuation_agent", valuation),
                ("coherence_agent", coherence),
            ] if v is not None
        ],
        "agents_skipped": [
            k for k, v in [
                ("earnings_analyst", earnings),
                ("valuation_agent", valuation),
                ("coherence_agent", coherence),
            ] if v is None
        ],
        "specialist_verdicts": aggregated["specialist_verdicts"],
        "panel_verdict": aggregated["panel_verdict"],
        "panel_verdict_explanation": aggregated["panel_verdict_explanation"],
        "earnings_summary": earnings.get("earnings_quality_rationale", "N/A") if earnings else "N/A",
        "valuation_summary": valuation.get("valuation_rationale", "N/A") if valuation else "N/A",
        "coherence_summary": coherence.get("coherence_rationale", "N/A") if coherence else "N/A",
        "final_disposition": coherence.get("final_disposition", "N/A") if coherence else "N/A",
    }

    out_path = out_dir / f"{ticker}_multi_agent_review.json"
    out_path.write_text(json.dumps(review, indent=2))
    print(f"[{ticker}] Multi-agent review → {out_path.name} (panel verdict: {review['panel_verdict']})")
    return review
