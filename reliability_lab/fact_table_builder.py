"""
Build and verify a fact table from extracted claims.

Each row: ticker, claim_type, metric, period, claimed_value,
          verified_value, source, verification_status, notes

Verification statuses: verified | incorrect | unsupported | not_machine_verifiable
"""
import csv
import json
from pathlib import Path

from reliability_lab.verifiers.sec_verifier import get_revenue, get_company_facts
from reliability_lab.verifiers.price_verifier import get_return
from reliability_lab.verifiers.fmp_verifier import (
    verify_eps, verify_pe_ratio, verify_ev_ebitda, verify_revenue_fmp,
    verify_ebitda_fmp,
    FMP_VERIFIERS,
)


VERIFICATION_STATUSES = [
    "verified",
    "incorrect",
    "unsupported",
    "not_machine_verifiable",
    "SOURCE_CONFLICT",
]

FACT_TABLE_COLUMNS = [
    "ticker",
    "claim_type",
    "metric",
    "period",
    "claimed_value",
    "verified_value",
    "source",
    "source_tier",
    "verification_status",
    "verified_value_alt",
    "source_alt",
    "conflict_details",
    "notes",
]

# Tolerance for revenue/financial figures: 2% rounding tolerance
_FINANCIAL_TOLERANCE = 0.02
# Tolerance for valuation multiples: 10% (more volatile)
_VALUATION_TOLERANCE = 0.10
# Tolerance for SOURCE_CONFLICT detection between Tier 1 and Tier 3
_CONFLICT_TOLERANCE_FINANCIAL = 0.05
_CONFLICT_TOLERANCE_EBITDA = 0.15


def _check_source_conflict(
    tier1_value: float,
    tier3_value: float,
    tolerance: float,
    tier1_display: str,
    tier1_source: str,
    tier3_display: str,
    tier3_source: str,
) -> tuple[str, str, str, str, str, str]:
    """
    Compare Tier 1 and Tier 3 values. Returns:
      (verified_value, source, source_tier, verification_status,
       verified_value_alt, source_alt, conflict_details_json)
    as a 7-tuple.
    Tier 1 wins when within tolerance (verified) or when in conflict (SOURCE_CONFLICT).
    """
    import json as _json
    delta_pct = abs(tier1_value - tier3_value) / max(abs(tier1_value), 1e-9)
    if delta_pct > tolerance:
        details = _json.dumps({
            "tier1_value": tier1_display,
            "tier3_value": tier3_display,
            "delta_pct": round(delta_pct, 4),
            "tolerance": tolerance,
        })
        return (tier1_display, tier1_source, "1",
                "SOURCE_CONFLICT",
                tier3_display, tier3_source, details)
    return (tier1_display, tier1_source, "1", "verified", "", "", "")


def _verify_revenue(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Returns (verified_value_str, status, source)."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    actual = get_revenue(ticker, year)
    if actual is None:
        return ("", "not_machine_verifiable", "SEC EDGAR: no data")

    diff = abs(actual - claimed) / max(abs(actual), 1)
    status = "verified" if diff <= _FINANCIAL_TOLERANCE else "incorrect"
    return (f"${actual/1e9:.2f}B", status, "SEC EDGAR 10-K")


def _verify_ebitda_sec(ticker: str, year: int) -> tuple[float | None, str, str]:
    """Return (raw_float, display_str, source_label) from SEC EDGAR, or (None, '', '')."""
    facts = get_company_facts(ticker)
    if not facts:
        return (None, "", "")

    gaap = facts.get("facts", {}).get("us-gaap", {})

    op_income = None
    for concept in ["OperatingIncomeLoss", "OperatingIncome"]:
        try:
            units = gaap[concept]["units"]["USD"]
            annual = [u for u in units if u.get("form") == "10-K" and u.get("fp") == "FY"
                      and str(u.get("end", "")).startswith(str(year))]
            if annual:
                op_income = float(annual[-1]["val"])
                break
        except (KeyError, TypeError):
            continue

    if op_income is None:
        return (None, "", "")

    da = None
    for concept in ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"]:
        try:
            units = gaap[concept]["units"]["USD"]
            annual = [u for u in units if u.get("form") == "10-K" and u.get("fp") == "FY"
                      and str(u.get("end", "")).startswith(str(year))]
            if annual:
                da = float(annual[-1]["val"])
                break
        except (KeyError, TypeError):
            continue

    if da is None:
        return (None, f"${op_income/1e9:.2f}B (op. income only)",
                "SEC EDGAR 10-K (D&A not found)")

    approx = op_income + da
    return (approx, f"${approx/1e9:.2f}B (op. income + D&A)", "SEC EDGAR 10-K")


def _verify_ebitda(
    ticker: str, period: str, claimed: float
) -> tuple[str, str, str, str, str, str]:
    """
    Dual-verify EBITDA via SEC EDGAR (Tier 1) and FMP (Tier 3).
    Returns (verified_value, source, source_tier, status, verified_value_alt, source_alt, conflict_details).
    """
    if not period:
        return ("", "not_machine_verifiable", "", "", "", "", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "", "", "", "", "")

    sec_raw, sec_display, sec_source = _verify_ebitda_sec(ticker, year)

    # FMP Tier 3 result (claimed value passed so we can get the raw display)
    fmp_display, fmp_status, fmp_source = verify_ebitda_fmp(ticker, period, claimed)

    # Parse FMP raw value from display string for comparison
    fmp_raw = None
    if fmp_display and fmp_status != "not_machine_verifiable":
        try:
            fmp_raw = float(fmp_display.replace("$", "").replace("B", "").split("(")[0].strip()) * 1e9
        except (ValueError, AttributeError):
            pass

    if sec_raw is not None and fmp_raw is not None:
        # Both sources returned a value — check for conflict
        result = _check_source_conflict(
            sec_raw, fmp_raw, _CONFLICT_TOLERANCE_EBITDA,
            sec_display, sec_source,
            fmp_display, fmp_source,
        )
        vv, src, tier, status, vv_alt, src_alt, cd = result
        # Also verify claimed value against the Tier 1 result
        if status == "verified":
            diff = abs(sec_raw - claimed) / max(abs(sec_raw), 1)
            status = "verified" if diff <= 0.15 else "incorrect"
        return (vv, src, tier, status, vv_alt, src_alt, cd)

    if sec_raw is not None:
        sec_display_full = f"${sec_raw/1e9:.2f}B (approx)" if not sec_display.endswith(")") else sec_display
        diff = abs(sec_raw - claimed) / max(abs(sec_raw), 1)
        status = "verified" if diff <= 0.15 else "incorrect"
        return (sec_display_full, "SEC EDGAR 10-K (op. income + D&A)", "1", status, "", "", "")

    if fmp_raw is not None:
        return (fmp_display, fmp_source, "3", fmp_status, "", "", "")

    return ("", "not_machine_verifiable", "", "", "", "", "")


def _verify_claim(claim: dict) -> dict:
    """Run the appropriate verifier and return an updated row dict."""
    ticker = claim.get("ticker", "")
    metric = claim.get("metric", "")
    period = claim.get("period", "")
    claimed_val = claim.get("value")
    claim_type = claim.get("claim_type", "")

    row = {
        "ticker": ticker,
        "claim_type": claim_type,
        "metric": metric,
        "period": str(period) if period else "",
        "claimed_value": claim.get("value_display", str(claimed_val) if claimed_val is not None else ""),
        "verified_value": "",
        "source": "",
        "source_tier": "",
        "verification_status": "unsupported",
        "verified_value_alt": "",
        "source_alt": "",
        "conflict_details": "",
        "notes": claim.get("claim_text", "")[:200],
    }

    if claimed_val is None:
        return row

    # Guidance/forward-looking claims can't be verified yet
    if claim_type == "guidance":
        row["verification_status"] = "not_machine_verifiable"
        row["source"] = "forward-looking (cannot verify against actuals)"
        return row

    # Year ceiling — projections (2026+) cannot be verified; 2025 actuals can be attempted
    if period and int(str(period)[:4]) > 2025:
        row["verification_status"] = "not_machine_verifiable"
        row["source"] = f"year {period} > 2025 — forward projection"
        return row

    # Peer comparison: note but don't attempt primary source check
    if claim_type == "peer-comparison":
        row["verification_status"] = "not_machine_verifiable"
        row["source"] = "peer comparison (secondary)"
        return row

    # Revenue — Tier 1: SEC EDGAR
    if metric == "revenue":
        v, status, source = _verify_revenue(ticker, period, float(claimed_val))
        row["verified_value"] = v
        row["verification_status"] = status
        row["source"] = source
        row["source_tier"] = "1" if v else ""
        return row

    # EBITDA — dual-verify Tier 1 (SEC) + Tier 3 (FMP), SOURCE_CONFLICT if they disagree
    if metric == "ebitda":
        vv, src, tier, status, vv_alt, src_alt, cd = _verify_ebitda(ticker, period, float(claimed_val))
        row["verified_value"] = vv
        row["source"] = src
        row["source_tier"] = tier
        row["verification_status"] = status
        row["verified_value_alt"] = vv_alt
        row["source_alt"] = src_alt
        row["conflict_details"] = cd
        return row

    # EPS — FMP income statement (Tier 3)
    if metric == "eps":
        v, status, source = verify_eps(ticker, period, float(claimed_val))
        row["verified_value"] = v
        row["verification_status"] = status
        row["source"] = source
        row["source_tier"] = "3" if v else ""
        return row

    # P/E ratio — FMP ratios (Tier 3)
    if metric == "pe_ratio":
        v, status, source = verify_pe_ratio(ticker, period, float(claimed_val))
        row["verified_value"] = v
        row["verification_status"] = status
        row["source"] = source
        row["source_tier"] = "3" if v else ""
        return row

    # EV/EBITDA — FMP ratios (Tier 3)
    if metric == "ev_ebitda":
        v, status, source = verify_ev_ebitda(ticker, period, float(claimed_val))
        row["verified_value"] = v
        row["verification_status"] = status
        row["source"] = source
        row["source_tier"] = "3" if v else ""
        return row

    # Percentage-based metrics — route to FMP verifier if available
    if claim.get("unit") == "percent":
        fn = FMP_VERIFIERS.get(metric)
        if fn is not None:
            v, status, source = fn(ticker, period, float(claimed_val))
            row["verified_value"] = v
            row["verification_status"] = status
            row["source"] = source
            row["source_tier"] = "3" if v else ""
            return row
        row["verification_status"] = "not_machine_verifiable"
        row["source"] = "percentage — no verifier for this metric"
        return row

    # Try FMP dispatch table for any remaining metrics
    fn = FMP_VERIFIERS.get(metric)
    if fn is not None:
        v, status, source = fn(ticker, period, float(claimed_val))
        row["verified_value"] = v
        row["verification_status"] = status
        row["source"] = source
        row["source_tier"] = "3" if v else ""
        return row

    row["verification_status"] = "not_machine_verifiable"
    row["source"] = "no verifier implemented for this metric"
    return row


def build_and_verify_fact_table(claims: list[dict], ticker: str) -> list[dict]:
    """
    Build and verify a fact table from extracted claims.
    Runs available verifiers and returns rows with verification status.
    """
    return [_verify_claim(c) for c in claims]


def build_fact_table(claims: list[dict], ticker: str) -> list[dict]:
    """Alias for backwards compatibility — runs verification."""
    return build_and_verify_fact_table(claims, ticker)


def save_fact_table(rows: list[dict], output_dir: str, ticker: str) -> Path:
    out = Path(output_dir) / f"{ticker}_fact_table.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FACT_TABLE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out
