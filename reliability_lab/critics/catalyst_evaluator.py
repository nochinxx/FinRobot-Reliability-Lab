"""
Catalyst Evaluator — G2 specialist agent.

Assesses whether the catalysts stated in an AI-generated equity research report are:
  - Specific: names a concrete event, product, date, or metric threshold
  - Timely: expected within a reasonable horizon (≤18 months)
  - Supported: corroborated by verified claims in the fact table

Output: output/{TICKER}/{TICKER}_catalyst_analysis.json
"""
import json
import re
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import _load_prompt, _make_run_metadata, _append_run_metadata
from reliability_lab.critic_agents import _llm_call

_CATALYST_KEYWORDS = {
    "earnings", "revenue", "guidance", "beat", "miss", "launch", "fda",
    "approval", "acquisition", "merger", "buyback", "dividend", "contract",
    "partnership", "expansion", "margin", "growth", "upgrade", "downgrade",
    "regulatory", "catalyst", "upcoming", "expected", "anticipated", "q1", "q2",
    "q3", "q4", "fy", "fiscal", "quarter", "year",
}

_VAGUE_PATTERNS = [
    r"\bcontinued\s+growth\b",
    r"\bstrong\s+fundamentals\b",
    r"\bpositive\s+momentum\b",
    r"\blong.term\s+potential\b",
    r"\bmarket\s+leadership\b",
    r"\bcompetitive\s+advantage\b",
    r"\bfavorable\s+macro\b",
]


def _extract_catalyst_claims(fact_rows: list[dict]) -> list[dict]:
    """Pull claims that look like forward-looking catalysts."""
    results = []
    for r in fact_rows:
        metric = r.get("metric", "").lower()
        claim_text = str(r.get("claim_text", r.get("claimed_value", ""))).lower()
        if any(kw in metric or kw in claim_text for kw in _CATALYST_KEYWORDS):
            results.append(r)
    return results[:20]


def _score_catalyst_specificity(catalyst_claims: list[dict]) -> dict:
    """Heuristic pre-scoring before LLM pass."""
    if not catalyst_claims:
        return {"specific": 0, "vague": 0, "total": 0, "specificity_rate": 0.0}

    specific, vague = 0, 0
    for c in catalyst_claims:
        text = str(c.get("claim_text", c.get("claimed_value", ""))).lower()
        is_vague = any(re.search(p, text) for p in _VAGUE_PATTERNS)
        # Specific if it contains a number, date pattern, or named event
        has_number = bool(re.search(r"\d", text))
        has_quarter = bool(re.search(r"\bq[1-4]\b|\bfy\d{2,4}\b", text))
        if has_number or has_quarter:
            specific += 1
        elif is_vague:
            vague += 1
        else:
            specific += 1  # neutral → give benefit of doubt

    total = len(catalyst_claims)
    return {
        "specific": specific,
        "vague": vague,
        "total": total,
        "specificity_rate": round(specific / total, 3) if total > 0 else 0.0,
    }


_CATALYST_PROMPT = """You are a buy-side analyst reviewing an AI-generated equity research report.
Your task: evaluate the quality of the stated investment catalysts.

TICKER: {ticker}
SCORECARD SUMMARY: {scorecard_summary}

CATALYST CLAIMS FROM FACT TABLE ({catalyst_count} items):
{catalyst_rows}

HEURISTIC PRE-SCORE:
{heuristic_score}

Evaluate each catalyst on three axes:
1. SPECIFIC — does it name a concrete event, product, date, or metric threshold? (not just "continued growth")
2. TIMELY — is it expected within 12-18 months? or is it perpetually "upcoming"?
3. SUPPORTED — is it corroborated by a verified fact in the table (status: verified/tier1)?

Then provide a verdict:
- STRONG: most catalysts are specific, timely, and supported
- ADEQUATE: mixed quality — some concrete, some vague
- WEAK: mostly vague, untimed, or unsupported forward claims

Respond with ONLY valid JSON:
{{
  "catalyst_verdict": "STRONG|ADEQUATE|WEAK",
  "specific_catalysts": ["..."],
  "vague_catalysts": ["..."],
  "unsupported_catalysts": ["..."],
  "specificity_rate": 0.0,
  "timeliness_note": "...",
  "support_note": "...",
  "summary": "2-3 sentence assessment of catalyst quality"
}}"""


def run_catalyst_evaluation(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
) -> Optional[dict]:
    """
    Run the Catalyst Evaluator agent.
    Returns the parsed analysis dict, or None if no LLM available.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    catalyst_claims = _extract_catalyst_claims(fact_rows)
    heuristic = _score_catalyst_specificity(catalyst_claims)

    def _fmt_row(r: dict) -> str:
        status = r.get("verification_status", "unverified")
        metric = r.get("metric", "")
        period = r.get("period", "")
        value = r.get("claimed_value", "")
        flag = "✅" if "verified" in status else ("❌" if status == "incorrect" else "○")
        return f"  {flag} [{metric}] ({period}): {value} [{status}]"

    catalyst_rows_str = "\n".join(_fmt_row(r) for r in catalyst_claims) or "  (no catalyst-type claims found)"

    m = scorecard.get("metrics", {})
    s = scorecard.get("summary", {})
    scorecard_summary = (
        f"Total claims: {s.get('total_claims', 0)} | "
        f"Verified: {s.get('verified_count', 0)} | "
        f"Incorrect: {s.get('incorrect_count', 0)} | "
        f"ICR: {m.get('incorrect_claim_rate', 'N/A')} | "
        f"SCR: {m.get('source_coverage_rate', 'N/A')}"
    )

    prompt = _CATALYST_PROMPT.format(
        ticker=ticker,
        scorecard_summary=scorecard_summary,
        catalyst_count=len(catalyst_claims),
        catalyst_rows=catalyst_rows_str,
        heuristic_score=json.dumps(heuristic, indent=2),
    )

    response_text, provider, model_name = _llm_call(prompt, max_tokens=1024)

    # Parse JSON from response
    result: Optional[dict] = None
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    if result is None:
        # Offline fallback — use heuristic only
        specificity_rate = heuristic["specificity_rate"]
        if specificity_rate >= 0.7:
            verdict = "STRONG"
        elif specificity_rate >= 0.4:
            verdict = "ADEQUATE"
        else:
            verdict = "WEAK"
        result = {
            "catalyst_verdict": verdict,
            "specific_catalysts": [],
            "vague_catalysts": [],
            "unsupported_catalysts": [],
            "specificity_rate": specificity_rate,
            "timeliness_note": "offline — heuristic only",
            "support_note": "offline — heuristic only",
            "summary": f"Offline fallback. Heuristic specificity rate: {specificity_rate:.1%}. {heuristic['total']} catalyst claims found.",
            "_offline_fallback": True,
        }

    result["heuristic_pre_score"] = heuristic
    result["catalyst_claim_count"] = len(catalyst_claims)

    # Save output
    out_path = out_dir / f"{ticker}_catalyst_analysis.json"
    out_path.write_text(json.dumps(result, indent=2))

    # Append run metadata
    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="G2-catalyst",
            model_name=model_name,
            provider=provider,
            temperature=0,
            prompt_file="catalyst_evaluator_v1.txt",
            prompt_text=_CATALYST_PROMPT,
            input_text=prompt,
            output_text=response_text,
        ),
        out_dir,
    )

    return result
