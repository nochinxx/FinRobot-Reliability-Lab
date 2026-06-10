"""
HTML table ingestion module.

Wraps tools/html_table_parser.py and converts structured table year-value pairs
into claim dicts compatible with claim.schema.json.

Injected into claim_extraction.py as a supplementary extraction pass.
Only runs when the report is an HTML file and BeautifulSoup is available.
"""
import re
import sys
from pathlib import Path
from typing import Optional

# Import table parser from tools/
_TOOLS = Path(__file__).parent.parent.parent / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

try:
    from html_table_parser import parse_report, _normalize_value  # noqa: F401
    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False


# Metric name normalization: raw table row label → claim schema metric name
_METRIC_MAP = {
    "revenue":                    "revenue",
    "revenues":                   "revenue",
    "total revenue":              "revenue",
    "net revenue":                "revenue",
    "ebitda":                     "ebitda",
    "adjusted ebitda":            "ebitda",
    "net income":                 "net_income",
    "net income (loss)":          "net_income",
    "earnings per share":         "eps",
    "eps":                        "eps",
    "diluted eps":                "eps",
    "diluted earnings per share": "eps",
    "p/e ratio":                  "pe_ratio",
    "price/earnings":             "pe_ratio",
    "pe ratio":                   "pe_ratio",
    "ev/ebitda":                  "ev_ebitda",
    "enterprise value/ebitda":    "ev_ebitda",
    "gross margin":               "gross_margin",
    "gross profit margin":        "gross_margin",
    "net margin":                 "net_margin",
    "net profit margin":          "net_margin",
    "ebitda margin":              "ebitda_margin",
    "free cash flow":             "free_cash_flow",
    "fcf":                        "free_cash_flow",
    "total debt":                 "total_debt",
    "market cap":                 "market_cap",
    "market capitalization":      "market_cap",
    "revenue growth":             "revenue_growth",
    "yoy revenue growth":         "revenue_growth",
}

# Claim type for each schema metric
_CLAIM_TYPE_MAP = {
    "revenue":        "financial",
    "ebitda":         "financial",
    "net_income":     "financial",
    "eps":            "financial",
    "pe_ratio":       "valuation",
    "ev_ebitda":      "valuation",
    "gross_margin":   "financial",
    "net_margin":     "financial",
    "ebitda_margin":  "financial",
    "free_cash_flow": "financial",
    "total_debt":     "financial",
    "market_cap":     "financial",
    "revenue_growth": "financial",
}

# Unit normalization: parser unit → claim schema unit
_UNIT_MAP = {
    "USD":      "USD",
    "percent":  "percent",
    "multiple": "multiple",
    "number":   "USD",    # plain numbers in financial tables assumed USD
}

_PERIOD_RE = re.compile(r"^(20\d{2})[AEae]?$")


def _normalize_period(period_str: Optional[str]) -> Optional[str]:
    """Strip trailing A/E from period string to get 4-digit year."""
    if not period_str:
        return None
    m = _PERIOD_RE.match(period_str.strip())
    if m:
        return m.group(1)
    # Accept FY2023 style (already cleaned by html_table_parser)
    if re.match(r"^20\d{2}$", period_str.strip()):
        return period_str.strip()
    return None


def _normalize_metric(raw_metric: str) -> Optional[str]:
    """Map raw table row label to claim schema metric name."""
    key = raw_metric.strip().lower()
    return _METRIC_MAP.get(key)


def table_claims_from_report(report_path: str, ticker: str) -> list[dict]:
    """
    Parse HTML report tables and return claim dicts for all structured
    year-value pairs with recognizable metrics.

    Returns [] if parsing fails, BeautifulSoup is unavailable, or report
    is not HTML.
    """
    if not HAS_PARSER:
        return []

    path = Path(report_path)
    if not path.exists() or path.suffix.lower() not in (".html", ".htm"):
        return []

    try:
        tables = parse_report(path)
    except Exception:
        return []

    claims = []
    seen = set()

    for table in tables:
        for pair in table.get("year_value_pairs", []):
            metric_raw = pair.get("metric", "")
            period_raw = pair.get("period")
            raw_value  = pair.get("raw_value", "")
            norm_value = pair.get("normalized_value")
            unit_raw   = pair.get("unit", "text")

            # Skip non-numeric and unrecognized units
            if norm_value is None or unit_raw not in _UNIT_MAP:
                continue

            metric = _normalize_metric(metric_raw)
            if not metric:
                continue

            period = _normalize_period(period_raw)
            unit   = _UNIT_MAP[unit_raw]

            # Deduplicate by (metric, period, value)
            key = (metric, period, norm_value)
            if key in seen:
                continue
            seen.add(key)

            claim_text = f"{metric_raw}: {raw_value} ({period_raw})"[:290]
            claims.append({
                "claim_text":        claim_text,
                "claim_type":        _CLAIM_TYPE_MAP.get(metric, "financial"),
                "metric":            metric,
                "unit":              unit,
                "period":            period,
                "value":             norm_value,
                "value_display":     raw_value,
                "source_status":     "unverified",
                "confidence":        "high",
                "extraction_method": "table_parser",
                "ticker":            ticker,
            })

    return claims
