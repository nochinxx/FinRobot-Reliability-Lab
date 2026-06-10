"""
Extract financial claims from a FinRobot HTML/text report.

Two extraction modes:
  1. regex  — deterministic, no API key, works now
  2. llm    — Claude-based structured extraction (requires ANTHROPIC_API_KEY)

Output: list of dicts with keys:
  claim_text, claim_type, ticker, metric, period, value, unit,
  source_status, confidence, extraction_method
"""
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


CLAIM_TYPES = [
    "financial",      # revenue, EBITDA, net income, EPS
    "valuation",      # P/E, EV/EBITDA, P/B, price target
    "stock-price",    # current price, 52-week range, return
    "guidance",       # forward estimates, projected figures
    "peer-comparison",# figures stated for peer companies
    "catalyst",       # event-driven claims
    "risk",           # risk factors
    "narrative",      # qualitative assertions (not verifiable numerically)
]


# ── HTML stripping ─────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = False

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


def _strip_html(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return " ".join(p.parts)


# ── Regex patterns ────────────────────────────────────────────────────────────

# Dollar + billion/million/trillion
_DOLLAR_BIG = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*(billion|trillion|million|B|M|T)\b',
    re.IGNORECASE
)
# Percentage
_PCT = re.compile(r'([\-\+]?\d+(?:\.\d+)?)\s*%')
# Multiples like 5.96x or 12.3x
_MULTIPLE = re.compile(r'\b([\d]+(?:\.\d+)?)\s*[xX]\b')
# EPS / per share like $6.34
_PER_SHARE = re.compile(r'\$\s*([\d]+(?:\.\d+)?)\s*(?:per share)?', re.IGNORECASE)

# Context keywords that help classify claims
_REVENUE_KW   = re.compile(r'\b(revenue|sales|turnover)\b', re.IGNORECASE)
_EBITDA_KW    = re.compile(r'\bebitda\b', re.IGNORECASE)
_EPS_KW       = re.compile(r'\b(eps|earnings per share)\b', re.IGNORECASE)
_PE_KW        = re.compile(r'\b(p/e|pe ratio|price.to.earnings)\b', re.IGNORECASE)
_EVEBITDA_KW  = re.compile(r'\bev/ebitda\b', re.IGNORECASE)
_PRICE_KW     = re.compile(r'\b(price|52.week|52 week|current price|target price)\b', re.IGNORECASE)
_GUIDANCE_KW  = re.compile(r'\b(forecast|project|expect|estimate|guided?|2025[AE]|2026[AE]|2027[AE])\b', re.IGNORECASE)
_PEER_KW      = re.compile(r'\b(peer|compared? (to|with)|versus|vs\.?)\b', re.IGNORECASE)
_CAGR_KW      = re.compile(r'\bcagr\b', re.IGNORECASE)
_YEAR_RE      = re.compile(r'(?<!\d)(20\d{2})(?!\d)')


def _window(text: str, pos: int, window: int = 120) -> str:
    """Return the substring around pos, for context."""
    start = max(0, pos - window)
    end = min(len(text), pos + window)
    return text[start:end]


_ESTIMATE_SUFFIX = re.compile(r'(20\d{2})[EAe]')  # e.g. 2025E, 2024A
_ESTIMATE_YEAR   = re.compile(r'\bFY(20\d{2})[Ee]\b|\b(20\d{2})[Ee]\b')


# Clause separators that bound year attribution in compound sentences.
# "from $27B in 2021 to $60B in 2022" — " to " prevents $60B from inheriting 2021.
_CLAUSE_SEP = re.compile(r'\s+to\s+|\s+from\s+', re.IGNORECASE)


def _find_year_in_range(text: str, range_start: int, range_end: int, ref_pos: int) -> tuple[str | None, bool]:
    """Return (year, is_estimate) for the nearest year in text[range_start:range_end]."""
    snippet = text[range_start:range_end]
    ref_offset = ref_pos - range_start
    best_year = None
    best_dist = float("inf")
    is_estimate = False
    for m in _YEAR_RE.finditer(snippet):
        dist = abs(m.start() - ref_offset)
        if dist < best_dist:
            best_dist = dist
            best_year = m.group(1)
            suffix_char = snippet[m.end():m.end()+1].upper()
            is_estimate = suffix_char == "E"
    return best_year, is_estimate


def _nearest_year(text: str, match_start: int, window: int = 200) -> tuple[str | None, bool]:
    """
    Find the year that belongs to the value at match_start.

    Uses clause-boundary detection to prevent cross-clause attribution: in compound
    sentences like "from $27B in 2021 to $60B in 2022", each value stays in its own
    clause and picks the correct year rather than the nearest one in the whole window.

    Falls back to raw nearest-year search if no clause boundary is found.
    Returns (year_str, is_estimate) where is_estimate=True for 2025E suffix.
    """
    full_start = max(0, match_start - window)
    full_end = min(len(text), match_start + window)
    before = text[full_start:match_start]
    after  = text[match_start:full_end]

    # Find nearest clause separator before match → clause starts right after it
    clause_start = full_start
    for m in _CLAUSE_SEP.finditer(before):
        clause_start = full_start + m.end()  # just after the separator

    # Find first clause separator after match → clause ends just before it
    clause_end = full_end
    m_after = _CLAUSE_SEP.search(after)
    if m_after:
        clause_end = match_start + m_after.start()

    # Search within the clause first
    year, is_est = _find_year_in_range(text, clause_start, clause_end, match_start)
    if year is not None:
        return year, is_est

    # No year found in clause → fall back to full window
    return _find_year_in_range(text, full_start, full_end, match_start)


def _normalize_value(amount: str, unit: str) -> float:
    """Convert dollar string + unit to a value in USD."""
    val = float(amount.replace(",", ""))
    unit = unit.upper().strip()
    if unit in ("BILLION", "B"):
        return val * 1e9
    if unit in ("TRILLION", "T"):
        return val * 1e12
    if unit in ("MILLION", "M"):
        return val * 1e6
    return val


def _classify_and_extract(text: str, match, metric_hint: str = "") -> Optional[dict]:
    """
    Given a regex match and surrounding context, return a claim dict or None.
    """
    ctx = _window(text, match.start())
    period, is_estimate = _nearest_year(text, match.start())

    # Determine claim type
    # CAGR alone doesn't indicate forward-looking — only "E" suffix or explicit future tense
    if is_estimate or _GUIDANCE_KW.search(ctx):
        claim_type = "guidance"
    elif _PEER_KW.search(ctx):
        claim_type = "peer-comparison"
    elif _PRICE_KW.search(ctx):
        claim_type = "stock-price"
    else:
        claim_type = "financial"

    # Determine metric
    if metric_hint:
        metric = metric_hint
    elif _REVENUE_KW.search(ctx):
        metric = "revenue"
    elif _EBITDA_KW.search(ctx):
        metric = "ebitda"
    elif _EPS_KW.search(ctx):
        metric = "eps"
    elif _PE_KW.search(ctx):
        metric = "pe_ratio"
        claim_type = "valuation"
    elif _EVEBITDA_KW.search(ctx):
        metric = "ev_ebitda"
        claim_type = "valuation"
    else:
        metric = "financial_figure"

    return {
        "claim_text": ctx.strip(),
        "claim_type": claim_type,
        "metric": metric,
        "period": period,
        "unit": "USD",
        "source_status": "unverified",
        "confidence": "medium",
        "extraction_method": "regex",
    }


def _extract_regex(text: str, ticker: str) -> list[dict]:
    claims = []
    seen_values = set()

    # 1. Dollar + billion/million/trillion figures
    for m in _DOLLAR_BIG.finditer(text):
        raw_val = m.group(1)
        unit = m.group(2)
        value_usd = _normalize_value(raw_val, unit)
        key = round(value_usd / 1e8)  # deduplicate at $100M granularity
        if key in seen_values:
            continue
        seen_values.add(key)
        claim = _classify_and_extract(text, m)
        if claim:
            claim["value"] = value_usd
            claim["value_display"] = f"${raw_val} {unit}"
            claims.append(claim)

    # 2. Valuation multiples (P/E and EV/EBITDA)
    # Use a narrow ±60-char window for classification so co-occurring keywords
    # (e.g. "P/E of 37.7x and EV/EBITDA of 28.5x") get the right metric each.
    _NARROW = 60
    for m in _MULTIPLE.finditer(text):
        pos = m.start()
        ns = max(0, pos - _NARROW)
        ne = min(len(text), pos + _NARROW)
        narrow_ctx = text[ns:ne]
        offset = pos - ns

        # Distance from match to nearest P/E keyword vs EV/EBITDA keyword
        def _min_dist(pattern):
            dists = [abs(km.start() - offset) for km in pattern.finditer(narrow_ctx)]
            return min(dists) if dists else float("inf")

        d_ev  = _min_dist(_EVEBITDA_KW)
        d_pe  = _min_dist(_PE_KW)
        if d_ev == float("inf") and d_pe == float("inf"):
            continue  # no valuation keyword nearby

        val    = float(m.group(1))
        period, is_est = _nearest_year(text, pos)
        metric = "ev_ebitda" if d_ev < d_pe else "pe_ratio"
        ctx    = _window(text, pos)
        claims.append({
            "claim_text": ctx.strip(),
            "claim_type": "valuation",
            "metric": metric,
            "period": period,
            "value": val,
            "value_display": f"{val}x",
            "unit": "multiple",
            "source_status": "unverified",
            "confidence": "medium",
            "extraction_method": "regex",
        })

    # 3. Percentage growth / margin figures with financial context
    for m in _PCT.finditer(text):
        ctx = _window(text, m.start())
        has_fin = any(kw.search(ctx) for kw in [_REVENUE_KW, _EBITDA_KW, _CAGR_KW])
        if not has_fin:
            continue
        val = float(m.group(1))
        period, is_est_pct = _nearest_year(text, m.start())
        metric = "revenue_growth" if _REVENUE_KW.search(ctx) else (
            "ebitda_margin" if _EBITDA_KW.search(ctx) else "growth_rate"
        )
        claims.append({
            "claim_text": ctx.strip(),
            "claim_type": "guidance" if _GUIDANCE_KW.search(ctx) else "financial",
            "metric": metric,
            "period": period,
            "value": val,
            "value_display": f"{val}%",
            "unit": "percent",
            "source_status": "unverified",
            "confidence": "medium",
            "extraction_method": "regex",
        })

    # Deduplicate by (metric, period, value_display)
    seen = set()
    unique = []
    for c in claims:
        key = (c["metric"], c["period"], c.get("value_display", ""))
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # Add ticker to all claims
    for c in unique:
        c["ticker"] = ticker

    return unique


# ── Prompt loading ────────────────────────────────────────────────────────────

def _load_prompt(name: str) -> str:
    """Load versioned prompt from prompts/{name}.txt. Raises if missing."""
    p = _PROMPTS_DIR / f"{name}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"Prompt file not found: {p}. "
        "Run from repo root or ensure prompts/ directory is present."
    )


# ── Run metadata helpers (P2-4) ───────────────────────────────────────────────

def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _make_run_metadata(
    ticker: str,
    phase: str,
    model_name: str,
    provider: str,
    temperature: float,
    prompt_file: Optional[str],
    prompt_text: Optional[str],
    input_text: Optional[str],
    output_text: Optional[str],
    claims_extracted: Optional[int] = None,
) -> dict:
    version = None
    if prompt_file:
        stem = Path(prompt_file).stem  # e.g. "claim_extractor_v1"
        parts = stem.rsplit("_v", 1)
        version = parts[1] if len(parts) == 2 else None
    return {
        "run_id":          str(uuid.uuid4()),
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "ticker":          ticker,
        "phase":           phase,
        "model_name":      model_name,
        "provider":        provider,
        "temperature":     temperature,
        "prompt_file":     prompt_file,
        "prompt_version":  version,
        "prompt_hash":     _sha256(prompt_text) if prompt_text else None,
        "input_hash":      _sha256(input_text)  if input_text  else None,
        "output_hash":     _sha256(output_text) if output_text else None,
        "fallback_used":   provider == "ollama_fallback",
        "source_tier":     None,
        "extraction_mode": "llm" if phase == "claim_extraction" else None,
        "claims_extracted": claims_extracted,
    }


def _append_run_metadata(metadata: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    p = output_dir / "run_metadata.json"
    existing = []
    if p.exists():
        try:
            existing = json.loads(p.read_text())
            if not isinstance(existing, list):
                existing = [existing]
        except json.JSONDecodeError:
            existing = []
    existing.append(metadata)
    p.write_text(json.dumps(existing, indent=2))


# ── LLM extraction (Claude) ───────────────────────────────────────────────────

_LLM_PROMPT = """You are a financial analyst auditing an equity research report.

Extract every specific, verifiable financial claim from the report text below.
Focus on quantitative claims: revenue, EBITDA, EPS, P/E, EV/EBITDA, price targets, returns.

For each claim return a JSON object with:
  - claim_text: the exact sentence or phrase containing the claim
  - claim_type: one of [financial, valuation, stock-price, guidance, peer-comparison]
  - metric: e.g. revenue, ebitda, eps, pe_ratio, ev_ebitda, price_target, return
  - period: fiscal year or date string (e.g. "2023", "2024E", "Q3 2023")
  - value: numeric value (in base units — dollars not billions)
  - value_display: how the value appears in the text (e.g. "$78.6 billion")
  - unit: USD, percent, multiple, or shares
  - confidence: high/medium/low

Return a JSON array. Only include claims with specific numeric values. Skip vague statements.

REPORT TEXT:
{report_text}
"""


def _extract_llm(
    text: str,
    ticker: str,
    max_chars: int = 12000,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """
    Claude-based extraction. Requires ANTHROPIC_API_KEY.
    If output_dir is provided, saves run_metadata.json alongside other outputs.
    """
    try:
        import anthropic
    except ImportError:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return []

    # Load prompt from file (P2-3); fall back to inline constant if file missing
    prompt_file = str(_PROMPTS_DIR / "claim_extractor_v1.txt")
    try:
        prompt_template = _load_prompt("claim_extractor_v1")
    except FileNotFoundError:
        prompt_template = _LLM_PROMPT

    truncated = text[:max_chars]
    prompt_text = prompt_template.format(report_text=truncated)

    client = anthropic.Anthropic(api_key=api_key)
    model_name = "claude-sonnet-4-6"
    msg = client.messages.create(
        model=model_name,
        max_tokens=4096,
        temperature=0,
        messages=[{"role": "user", "content": prompt_text}],
    )

    raw = msg.content[0].text.strip()

    # Extract JSON array from response
    start = raw.find("[")
    end = raw.rfind("]") + 1
    claims = []
    if start != -1 and end > start:
        try:
            claims = json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass

    for c in claims:
        c["ticker"] = ticker
        c["extraction_method"] = "llm"
        c.setdefault("source_status", "unverified")
        c["prompt_version"] = "claim_extractor_v1"
        c["model_name"] = model_name
        c["provider"] = "anthropic"

    # Record run metadata (P2-4)
    if output_dir is not None:
        meta = _make_run_metadata(
            ticker=ticker,
            phase="claim_extraction",
            model_name=model_name,
            provider="anthropic",
            temperature=0,
            prompt_file=prompt_file,
            prompt_text=prompt_template,
            input_text=truncated,
            output_text=raw,
            claims_extracted=len(claims),
        )
        _append_run_metadata(meta, Path(output_dir))

    return claims


# ── Public API ────────────────────────────────────────────────────────────────

def _supplement_with_table_claims(
    base_claims: list[dict],
    report_path: str,
    ticker: str,
) -> list[dict]:
    """
    Augment base_claims with table-parsed claims that have no matching
    (metric, period) entry in base_claims. Table claims add structured
    coverage that _strip_html() destroys.
    """
    try:
        from reliability_lab.ingestion.html_tables import table_claims_from_report
    except ImportError:
        return base_claims

    table_claims = table_claims_from_report(report_path, ticker)
    if not table_claims:
        return base_claims

    # Build existing (metric, period) coverage set
    existing = {
        (c.get("metric"), str(c.get("period") or ""))
        for c in base_claims
    }

    added = []
    for tc in table_claims:
        key = (tc.get("metric"), str(tc.get("period") or ""))
        if key not in existing:
            added.append(tc)
            existing.add(key)

    return base_claims + added


def extract_claims_from_report(
    report_path: str,
    ticker: str,
    mode: str = "auto"
) -> list[dict]:
    """
    Extract claims from a FinRobot report file (HTML or text).

    mode:
      "regex" — deterministic only (no API key required)
      "llm"   — Claude-based only (requires ANTHROPIC_API_KEY)
      "auto"  — try LLM first, fall back to regex

    After primary extraction, table-parsed claims from HTML tables are
    appended for any (metric, period) pair not already covered.
    """
    report = Path(report_path)
    if not report.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    raw = report.read_text(encoding="utf-8")
    # Strip HTML if needed
    text = _strip_html(raw) if raw.strip().startswith("<") else raw

    if mode == "llm":
        base = _extract_llm(text, ticker)
    elif mode == "regex":
        base = _extract_regex(text, ticker)
    else:
        # auto: try LLM, fall back to regex
        if os.environ.get("ANTHROPIC_API_KEY"):
            llm_claims = _extract_llm(text, ticker)
            if llm_claims:
                base = llm_claims
            else:
                base = _extract_regex(text, ticker)
        else:
            base = _extract_regex(text, ticker)

    return _supplement_with_table_claims(base, report_path, ticker)


def save_claims(claims: list[dict], output_dir: str, ticker: str) -> Path:
    out = Path(output_dir) / f"{ticker}_claims.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(claims, indent=2))
    return out
