"""
critic_agents.py — Phase 5: adversarial critique loop.

Two-agent review:
  1. Skeptical Analyst  — challenges the weakest/unsupported claims
  2. Thesis Synthesizer — weighs critic findings, writes audited memo

Outputs (in output/<TICKER>/):
  <TICKER>_critic_findings.json   — structured per-claim challenges
  <TICKER>_thesis_change.md       — what changed after adversarial review
  <TICKER>_audited_memo.md        — final investment memo post-critique

Thesis Stability Score:
  = 1 - (thesis-changing challenges / total challenges)
  1.0 = thesis unchanged; 0.0 = thesis completely overturned
"""

import json
import os
import requests
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import (
    _load_prompt, _make_run_metadata, _append_run_metadata,
)

_OLLAMA_BASE = "http://127.0.0.1:11434"
_OLLAMA_MODEL = "gemma4:12b-mlx"


def _llm_call(prompt: str, max_tokens: int = 2048) -> tuple[str, str, str]:
    """
    Call the best available LLM: Anthropic first, then Ollama local fallback.
    Returns (response_text, provider, model_name).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            _model = "claude-sonnet-4-6"
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model=_model,
                max_tokens=max_tokens,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip(), "anthropic", _model
        except Exception as e:
            print(f"  [critic] Anthropic API error: {e} — falling back to Ollama")

    # Ollama fallback — use chat endpoint with think=False to avoid empty responses
    ollama_tokens = min(max_tokens, 1024)
    try:
        resp = requests.post(
            f"{_OLLAMA_BASE}/api/chat",
            json={
                "model": _OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": ollama_tokens,
                    "num_ctx": 8192,
                    "temperature": 0.1,
                },
            },
            timeout=600,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip(), "ollama_fallback", _OLLAMA_MODEL
    except Exception as e:
        print(f"  [critic] Ollama error: {e}")
        return "", "none", "none"


_SKEPTIC_PROMPT = """\
You are a skeptical buy-side analyst reviewing an AI-generated equity research report.

RELIABILITY SCORECARD:
{metrics_summary}

INCORRECTLY VERIFIED CLAIMS (these were confirmed wrong by primary sources):
{incorrect_claims}

UNSUPPORTED CLAIMS (no primary source could verify these):
{unsupported_claims}

REPORT SUMMARY (first 3000 chars):
{report_excerpt}

Your task:
1. Identify the 3-5 WEAKEST claims — unsupported, cherry-picked, or contradicted by the fact table
2. For each, state: what the report claims, why you doubt it, what the likely actual figure is
3. State whether each challenge changes the investment thesis or is just a minor factual error
4. Give a REVISED recommendation (buy / hold / sell / avoid) reflecting corrections

Return ONLY a JSON object (no markdown fences):
{{
  "challenges": [
    {{
      "original_claim": "exact phrase from report",
      "challenge": "why this is wrong or unsupported",
      "likely_actual": "what the real figure likely is",
      "thesis_impact": "changes_thesis" | "minor_factual" | "confirms_thesis",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "revised_recommendation": "buy" | "hold" | "sell" | "avoid",
  "revised_rationale": "2-3 sentence rationale",
  "thesis_stability_score": 0.0
}}
"""

_SYNTHESIS_PROMPT = """\
You are writing a final audited investment memo after adversarial review.

TICKER: {ticker}
ORIGINAL FINROBOT RECOMMENDATION: {original_recommendation}

VERIFIED FACTS (confirmed against primary sources):
{verified_facts}

CRITIC CHALLENGES:
{critic_findings}

Write a structured 3-paragraph memo. No preamble. Start directly with the content.

Paragraph 1 — What the original analysis got right (use verified facts with numbers)
Paragraph 2 — What the adversarial review changed (name each major challenge and its implication)
Paragraph 3 — Final recommendation with key risk/upside asymmetry (be specific and numeric)
"""


def _extract_original_recommendation(report_text: str) -> str:
    """Best-effort extract the recommendation from the report."""
    import re
    for pat in [
        r"recommendation[:\s]+(buy|hold|sell|strong buy|strong sell|outperform|underperform)",
        r"(buy|hold|sell|outperform|underperform)\s+recommendation",
        r"we\s+(recommend|rate)\s+(buy|hold|sell)",
    ]:
        m = re.search(pat, report_text[:4000], re.IGNORECASE)
        if m:
            groups = [g for g in m.groups() if g]
            return groups[-1].upper()
    return "HOLD (inferred)"


def _format_fact_rows(rows: list[dict], status_filter: str) -> str:
    subset = [r for r in rows if r.get("verification_status") == status_filter]
    if not subset:
        return "  (none)"
    lines = []
    for r in subset[:10]:
        lines.append(
            f"  - {r['metric']} ({r['period']}): claimed {r['claimed_value']}"
            + (f", actual {r['verified_value']}" if r.get('verified_value') else "")
            + f" | {r.get('notes', '')[:80]}"
        )
    return "\n".join(lines)


def run_critic_review(
    ticker: str,
    report_path: str,
    fact_rows: list[dict],
    scorecard: dict,
    output_dir: str,
) -> Optional[dict]:
    """
    Run adversarial critic review.
    Uses Anthropic Claude if ANTHROPIC_API_KEY is set; falls back to Ollama local.
    Returns None only if both LLMs are unavailable.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read report text
    rp = Path(report_path)
    if not rp.exists():
        print(f"[{ticker}] critic_agents: report not found at {report_path}")
        return None
    report_raw = rp.read_text(encoding="utf-8")

    # Strip HTML
    from html.parser import HTMLParser

    class _Strip(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts, self._skip = [], False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                s = data.strip()
                if s:
                    self.parts.append(s)

    p = _Strip()
    p.feed(report_raw)
    report_text = " ".join(p.parts)

    m = scorecard.get("metrics", {})
    metrics_summary = (
        f"  SCR (source coverage): {m.get('source_coverage_rate', 'N/A'):.3f} "
        f"(target ≥0.80)\n"
        f"  ICR (incorrect claim rate): {m.get('incorrect_claim_rate', 'N/A')}\n"
        f"  Valuation dispersion: {m.get('valuation_dispersion', 'N/A')}\n"
        f"  Total claims: {scorecard.get('summary', {}).get('total_claims', 0)}, "
        f"verified: {scorecard.get('summary', {}).get('verified_count', 0)}, "
        f"incorrect: {scorecard.get('summary', {}).get('incorrect_count', 0)}"
    )

    print(f"[{ticker}] Running Skeptical Analyst agent...")
    try:
        _skeptic_tmpl = _load_prompt("skeptical_analyst_v1")
        # File uses single braces — use explicit replacement to avoid JSON brace conflicts
        skeptic_prompt = (
            _skeptic_tmpl
            .replace("{metrics_summary}", metrics_summary)
            .replace("{incorrect_claims}", _format_fact_rows(fact_rows, "incorrect"))
            .replace("{unsupported_claims}", _format_fact_rows(fact_rows, "unsupported"))
            .replace("{report_excerpt}", report_text[:1500])
        )
    except FileNotFoundError:
        _skeptic_tmpl = _SKEPTIC_PROMPT
        skeptic_prompt = _SKEPTIC_PROMPT.format(
            metrics_summary=metrics_summary,
            incorrect_claims=_format_fact_rows(fact_rows, "incorrect"),
            unsupported_claims=_format_fact_rows(fact_rows, "unsupported"),
            report_excerpt=report_text[:1500],
        )

    raw, _skeptic_provider, _skeptic_model = _llm_call(skeptic_prompt, max_tokens=2048)
    if not raw:
        print(f"[{ticker}] Skeptical Analyst returned empty response — skipping")
        return None

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="skeptical_analyst",
            model_name=_skeptic_model,
            provider=_skeptic_provider,
            temperature=0 if _skeptic_provider == "anthropic" else 0.1,
            prompt_file="skeptical_analyst_v1.txt",
            prompt_text=_skeptic_tmpl,
            input_text=skeptic_prompt,
            output_text=raw,
        ),
        out_dir,
    )

    # Parse JSON response
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    critic_data: dict = {}
    if start != -1 and end > start:
        try:
            critic_data = json.loads(raw[start:end])
        except json.JSONDecodeError:
            critic_data = {"raw_response": raw, "parse_error": True}
    else:
        critic_data = {"raw_response": raw, "parse_error": True}

    # Compute thesis stability if not provided by the model
    if "thesis_stability_score" not in critic_data or critic_data.get("parse_error"):
        challenges = critic_data.get("challenges", [])
        if challenges:
            thesis_changers = sum(
                1 for c in challenges if c.get("thesis_impact") == "changes_thesis"
            )
            critic_data["thesis_stability_score"] = round(
                1 - thesis_changers / len(challenges), 3
            )
        else:
            critic_data["thesis_stability_score"] = 1.0

    # Save critic findings
    findings_path = out_dir / f"{ticker}_critic_findings.json"
    findings_path.write_text(json.dumps(critic_data, indent=2))
    print(f"[{ticker}] Critic findings → {findings_path}")

    # Build thesis change log
    original_rec = _extract_original_recommendation(report_text)
    revised_rec  = critic_data.get("revised_recommendation", "N/A").upper()
    stability    = critic_data.get("thesis_stability_score", 1.0)
    challenges   = critic_data.get("challenges", [])

    change_lines = [
        f"# Thesis Change Log — {ticker}",
        "",
        f"**Original recommendation:** {original_rec}",
        f"**Post-critic recommendation:** {revised_rec}",
        f"**Thesis stability score:** {stability:.3f}  "
        f"({'stable' if stability >= 0.7 else 'materially changed' if stability >= 0.4 else 'overturned'})",
        "",
        "## Challenges",
        "",
    ]
    for i, ch in enumerate(challenges, 1):
        impact = ch.get("thesis_impact", "unknown")
        sev    = ch.get("severity", "medium")
        change_lines += [
            f"### {i}. [{sev.upper()} / {impact}]",
            f"**Claimed:** {ch.get('original_claim', '')}",
            f"**Challenge:** {ch.get('challenge', '')}",
            f"**Likely actual:** {ch.get('likely_actual', '')}",
            "",
        ]

    change_path = out_dir / f"{ticker}_thesis_change.md"
    change_path.write_text("\n".join(change_lines))
    print(f"[{ticker}] Thesis change log → {change_path}")

    # Phase 2: Synthesis agent — write audited memo
    verified_facts_str = _format_fact_rows(fact_rows, "verified")
    critic_findings_str = json.dumps(challenges[:5], indent=2) if challenges else "(none)"

    print(f"[{ticker}] Running Thesis Synthesizer agent...")
    try:
        _synth_tmpl = _load_prompt("thesis_synthesizer_v1")
        synth_prompt = (
            _synth_tmpl
            .replace("{ticker}", ticker)
            .replace("{original_recommendation}", original_rec)
            .replace("{verified_facts}", verified_facts_str)
            .replace("{critic_findings}", critic_findings_str)
        )
    except FileNotFoundError:
        _synth_tmpl = _SYNTHESIS_PROMPT
        synth_prompt = _SYNTHESIS_PROMPT.format(
            ticker=ticker,
            original_recommendation=original_rec,
            verified_facts=verified_facts_str,
            critic_findings=critic_findings_str,
        )

    audited_memo, _synth_provider, _synth_model = _llm_call(synth_prompt, max_tokens=1024)
    if not audited_memo:
        audited_memo = "(synthesis agent failed)"

    _append_run_metadata(
        _make_run_metadata(
            ticker=ticker,
            phase="thesis_synthesizer",
            model_name=_synth_model,
            provider=_synth_provider,
            temperature=0 if _synth_provider == "anthropic" else 0.1,
            prompt_file="thesis_synthesizer_v1.txt",
            prompt_text=_synth_tmpl,
            input_text=synth_prompt,
            output_text=audited_memo,
        ),
        out_dir,
    )

    memo_path = out_dir / f"{ticker}_audited_memo.md"
    memo_path.write_text(
        f"# Audited Investment Memo — {ticker}\n\n"
        f"*Original: {original_rec} → Post-critique: {revised_rec} "
        f"(stability {stability:.3f})*\n\n"
        + audited_memo
    )
    print(f"[{ticker}] Audited memo → {memo_path}")

    return {
        "ticker": ticker,
        "original_recommendation": original_rec,
        "revised_recommendation": revised_rec,
        "thesis_stability_score": stability,
        "findings_path": str(findings_path),
        "memo_path": str(memo_path),
    }
