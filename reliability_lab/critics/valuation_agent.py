"""
Valuation Agent — G2 specialist agent.

Evaluates the valuation analysis section of an AI-generated equity research report:
  - Multiple reasonableness vs. sector norms
  - Internal consistency across P/E, EV/EBITDA, other multiples
  - Peer comparison validity
  - Price target consistency

Output: output/{TICKER}/{TICKER}_valuation_analysis.json
"""
import json
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call

_VALUATION_METRICS = {"pe_ratio", "ev_ebitda", "price_to_sales", "price_to_book",
                      "market_cap", "enterprise_value", "dividend_yield"}

_SECTOR_PE_RANGES = {
    "Technology": (20, 80),
    "Healthcare": (15, 50),
    "Finance": (8, 20),
    "Consumer Staples": (15, 30),
    "Consumer Discretionary": (15, 40),
    "Industrials": (15, 30),
    "Energy": (10, 25),
    "Materials": (10, 25),
    "Real Estate": (20, 50),
    "Utilities": (15, 30),
    "Communication Services": (15, 40),
    "Unknown": (5, 100),
}


def _infer_sector(ticker: str, fact_rows: list[dict]) -> str:
    """Best-effort sector inference from fact table or known mappings."""
    _KNOWN = {
        "NVDA": "Technology", "MSFT": "Technology", "META": "Technology",
        "AAPL": "Technology", "GOOGL": "Technology", "AMZN": "Technology",
        "TSLA": "Consumer Discretionary", "COP": "Energy",
        "ETSY": "Consumer Discretionary", "ROKU": "Technology",
        "RIVN": "Consumer Discretionary", "RBLX": "Technology", "LCID": "Consumer Discretionary",
        "JPM": "Finance", "BAC": "Finance", "GS": "Finance", "MS": "Finance",
        "JNJ": "Healthcare", "PFE": "Healthcare", "UNH": "Healthcare",
        "WMT": "Consumer Staples", "KO": "Consumer Staples", "PG": "Consumer Staples",
        "NEE": "Utilities", "DUK": "Utilities",
        "AMT": "Real Estate", "PLD": "Real Estate",
    }
    return _KNOWN.get(ticker, "Unknown")


def _format_valuation_rows(fact_rows: list[dict]) -> str:
    rows = [r for r in fact_rows if r.get("metric", "") in _VALUATION_METRICS]
    if not rows:
        return "  (no valuation multiples verified in this run)"
    lines = []
    for r in rows:
        status = r.get("verification_status", "unsupported")
        flag = "❌" if status == "incorrect" else ("✅" if status == "verified" else "○")
        verified = r.get("verified_value", "")
        claimed = r.get("claimed_value", "")
        if verified:
            lines.append(f"  {flag} {r.get('metric')} ({r.get('period')}): "
                         f"claimed={claimed}, verified={verified}")
        else:
            lines.append(f"  {flag} {r.get('metric')} ({r.get('period')}): "
                         f"claimed={claimed}, status={status}")
    return "\n".join(lines) or "  (no valuation rows)"


def run_valuation_analysis(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
) -> Optional[dict]:
    """
    Run the Valuation Agent.
    Returns the parsed analysis dict, or None if no LLM available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sector = _infer_sector(ticker, fact_rows)
    vd = scorecard.get("metrics", {}).get("valuation_dispersion")
    vd_str = f"{vd:.3f}" if vd is not None else "N/A"
    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    scorecard_summary = (
        f"  Total claims: {s.get('total_claims', 0)} | "
        f"VD: {vd_str} | SCR: {m.get('source_coverage_rate', 'N/A')}"
    )

    valuation_rows = _format_valuation_rows(fact_rows)

    try:
        tmpl = _load_prompt("valuation_agent_v1")
    except FileNotFoundError:
        print(f"[{ticker}] valuation_agent: prompt file not found")
        return None

    prompt = (
        tmpl
        .replace("{ticker}", ticker)
        .replace("{sector}", sector)
        .replace("{valuation_rows}", valuation_rows)
        .replace("{valuation_dispersion}", vd_str)
        .replace("{scorecard_summary}", scorecard_summary)
    )

    print(f"[{ticker}] Running Valuation Agent...")
    raw, provider, model_name = _llm_call(prompt, max_tokens=1024)
    if not raw:
        print(f"[{ticker}] Valuation Agent: no LLM response")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="valuation_agent",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="valuation_agent_v1.txt",
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
                "valuation_verdict": "unknown",
                "valuation_rationale": raw[:500],
            }
    else:
        result = {
            "valuation_verdict": "unknown",
            "valuation_rationale": raw[:500],
        }

    # Inject computed fields
    val_rows = [r for r in fact_rows if r.get("metric", "") in _VALUATION_METRICS]
    pe_range = _SECTOR_PE_RANGES.get(sector, _SECTOR_PE_RANGES["Unknown"])
    result["_computed"] = {
        "sector": sector,
        "valuation_dispersion": vd,
        "valuation_claims_total": len(val_rows),
        "expected_pe_range": pe_range,
    }

    out_path = out_dir / f"{ticker}_valuation_analysis.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"[{ticker}] Valuation analysis → {out_path.name}")
    return result
