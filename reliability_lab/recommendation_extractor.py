"""
Extract the structured investment recommendation from a FinRobot HTML report.

Uses the LLM to parse rating, price target, catalysts, risks, and thesis.

Output (in output/{TICKER}/):
  {TICKER}_recommendation.json
  run_metadata.json (appended)
"""
import json
import os
from pathlib import Path
from typing import Optional

from reliability_lab.claim_extraction import (
    _strip_html, _load_prompt, _make_run_metadata, _append_run_metadata,
)

_FALLBACK_PROMPT = "Extract the investment recommendation as JSON from:\n\n{report_text}"


def extract_recommendation(
    report_path: str,
    ticker: str,
    output_dir: Optional[str] = None,
) -> Optional[dict]:
    """
    Extract structured recommendation from a FinRobot HTML report via Claude.
    Returns None when ANTHROPIC_API_KEY is absent (e.g. DEV_MODE tests).
    Saves {TICKER}_recommendation.json and appends to run_metadata.json.
    """
    try:
        import anthropic
    except ImportError:
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    rp = Path(report_path)
    if not rp.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    raw_html = rp.read_text(encoding="utf-8")
    text = _strip_html(raw_html) if raw_html.strip().startswith("<") else raw_html
    truncated = text[:12000]

    prompt_file = "recommendation_extractor_v1.txt"
    try:
        prompt_template = _load_prompt("recommendation_extractor_v1")
    except FileNotFoundError:
        prompt_template = _FALLBACK_PROMPT

    # Use explicit replacement — prompt file contains literal JSON braces
    prompt_text = prompt_template.replace("{report_text}", truncated)

    model_name = "claude-sonnet-4-6"
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model_name,
        max_tokens=2048,
        temperature=0,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw_response = msg.content[0].text.strip()

    # Extract JSON object from response
    start = raw_response.find("{")
    end = raw_response.rfind("}") + 1
    if start != -1 and end > start:
        try:
            recommendation = json.loads(raw_response[start:end])
        except json.JSONDecodeError:
            recommendation = {"raw_response": raw_response, "parse_error": True}
    else:
        recommendation = {"raw_response": raw_response, "parse_error": True}

    if not recommendation.get("parse_error"):
        recommendation["ticker"] = ticker
        recommendation["extraction_method"] = "llm"
        recommendation["model_name"] = model_name
        recommendation["provider"] = "anthropic"

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        rec_path = out / f"{ticker}_recommendation.json"
        rec_path.write_text(json.dumps(recommendation, indent=2))
        _append_run_metadata(
            _make_run_metadata(
                ticker=ticker,
                phase="recommendation_extraction",
                model_name=model_name,
                provider="anthropic",
                temperature=0,
                prompt_file=prompt_file,
                prompt_text=prompt_template,
                input_text=truncated,
                output_text=raw_response,
            ),
            out,
        )

    return recommendation
