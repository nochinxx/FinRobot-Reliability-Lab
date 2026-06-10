"""
Investment Committee Memo — Phase 7.

Produces an institutional-grade memo using ONLY the locked fact base
(verified Tier 1 claims) plus the audited recommendation and scorecard.

Rules from prompt:
  - No unsupported claims
  - Every number from the locked fact base
  - Prominent WARNING if SCR < 0.80 or ICR > 0.10
  - Gate decision included prominently

Output: output/{TICKER}/{TICKER}_investment_committee_memo.md
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call


def _build_locked_facts(fact_rows: list[dict]) -> str:
    """Format verified/locked fact rows as a bullet list for the LLM."""
    locked = [
        r for r in fact_rows
        if r.get("verification_status") == "verified"
    ]
    if not locked:
        return "  (no verified claims available — all claims unverified or not machine-verifiable)"
    lines = []
    for r in locked:
        tier = r.get("source_tier", "")
        tier_label = f"[Tier {tier}]" if tier else "[Tier ?]"
        lines.append(
            f"  {tier_label} {r['metric']} ({r['period']}): "
            f"{r['claimed_value']} → verified {r['verified_value']} "
            f"via {r['source']}"
        )
    return "\n".join(lines)


def _build_recommendation_str(output_dir: str, ticker: str) -> str:
    rec_path = Path(output_dir) / f"{ticker}_recommendation.json"
    if not rec_path.exists():
        return "(recommendation.json not found — run with --recommendation)"
    try:
        rec = json.loads(rec_path.read_text())
        rating  = rec.get("rating", {}).get("value", "N/A")
        pt      = rec.get("price_target", {}).get("value", "N/A")
        horizon = rec.get("investment_horizon", "N/A")
        rationale = rec.get("thesis", {}).get("bull_case", "")[:300]
        return (
            f"Rating: {rating}\n"
            f"Price target: {pt}\n"
            f"Horizon: {horizon}\n"
            f"Thesis (bull case): {rationale}"
        )
    except Exception:
        return "(could not parse recommendation.json)"


def _build_scorecard_str(scorecard: dict, gate: Optional[dict] = None) -> str:
    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    decision = gate.get("decision", "N/A") if gate else "N/A (--gate not run)"
    lines = [
        f"  Source coverage rate:    {m.get('source_coverage_rate', 'N/A'):.3f}",
        f"  Incorrect claim rate:    {m.get('incorrect_claim_rate', 'N/A')}",
        f"  Machine-verifiable:      {s.get('machine_verifiable_claims', 0)} / {s.get('total_claims', 0)}",
        f"  Gate decision:           {decision}",
    ]
    return "\n".join(lines)


def run_investment_committee_memo(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    gate: Optional[dict] = None,
) -> Optional[str]:
    """
    Generate an investment committee memo using verified facts and audited recommendation.
    Returns the memo text, or None if no LLM is available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    locked_facts   = _build_locked_facts(fact_rows)
    recommendation = _build_recommendation_str(output_dir, ticker)
    scorecard_str  = _build_scorecard_str(scorecard, gate)

    try:
        tmpl = _load_prompt("investment_committee_memo_v1")
    except FileNotFoundError:
        print(f"[{ticker}] investment_committee_memo: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{locked_facts}", locked_facts)
        .replace("{recommendation}", recommendation)
        .replace("{scorecard}", scorecard_str)
    )

    print(f"[{ticker}] Running Investment Committee Memo writer...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=2048)
    if not raw:
        print(f"[{ticker}] IC Memo: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="investment_committee_memo",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="investment_committee_memo_v1.txt",
            prompt_text=tmpl,
            input_text=prompt,
            output_text=raw,
        ),
        out_dir,
    )

    # Add preamble with WARNING if metrics breach thresholds
    m = scorecard.get("metrics", {})
    scr = m.get("source_coverage_rate", 1.0) or 1.0
    icr = m.get("incorrect_claim_rate", 0.0) or 0.0
    warning = ""
    if scr < 0.80 or icr > 0.10:
        warning = (
            f"> ⚠️ WARNING: SCR={scr:.3f} (threshold ≥0.80), ICR={icr:.3f} "
            f"(threshold ≤0.10). This memo is based on limited verification. "
            f"Human review required before acting on this recommendation.\n\n"
        )

    memo = (
        f"# Investment Committee Memo — {ticker}\n\n"
        + warning
        + raw
    )

    out_path = out_dir / f"{ticker}_investment_committee_memo.md"
    out_path.write_text(memo)
    print(f"[{ticker}] IC memo → {out_path}")
    return memo
