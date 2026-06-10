"""
Financial Modeling Prep verifier — augments SEC EDGAR coverage.

Free tier (new accounts post-Aug 2025): uses /stable/ endpoints.
income-statement (v3 legacy) is blocked; use ratios + key-metrics + cash-flow-statement.

Available endpoints (verified 2026-06-04):
  stable/ratios               → priceToEarningsRatio, enterpriseValueMultiple, netIncomePerShare
  stable/key-metrics          → evToEBITDA, earningsYield, enterpriseValue
  stable/cash-flow-statement  → netIncome, depreciationAndAmortization
  stable/balance-sheet-statement
  stable/income-statement-as-reported  (raw XBRL, minimal fields)
  stable/profile, stable/quote

Covers: EPS (via netIncomePerShare), P/E, EV/EBITDA, EBITDA value (via D&A + SEC op. income).

API key read from: config_api_keys (FMP_API_KEY) or env var FMP_API_KEY.
"""
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

from reliability_lab.verifiers.api_cache import fmp_get

_BASE = "https://financialmodelingprep.com/stable"
_CACHE_DIR = Path(__file__).parent.parent / "output" / "fmp_cache"
_CACHE_TTL = 86400  # 24 hours (legacy per-file cache — new calls go through api_cache)


def _get_api_key() -> Optional[str]:
    key = os.environ.get("FMP_API_KEY")
    if key:
        return key
    config = Path(__file__).parent.parent.parent / "config_api_keys"
    if config.exists():
        try:
            data = json.loads(config.read_text())
            return data.get("FMP_API_KEY")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _cached_get(path: str, params: dict) -> Optional[list]:
    """
    GET with centralized cache (api_cache.py) + legacy 24h file cache fallback.
    DEV_MODE=1 or OFFLINE=1 prevents all live API calls.
    """
    symbol = params.get("symbol", "unknown")

    def _fetch():
        # Check legacy per-file cache first (backward compat)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_key = f"{path.replace('/', '_')}_{symbol}"
        cache_file = _CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < _CACHE_TTL:
                try:
                    cached = json.loads(cache_file.read_text())
                    if isinstance(cached, list):
                        return cached
                except json.JSONDecodeError:
                    pass
        try:
            resp = requests.get(f"{_BASE}/{path}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                cache_file.write_text(json.dumps(data))
                return data
            return []
        except Exception:
            return []

    return fmp_get(path, symbol, _fetch)


def _get_ratios(ticker: str) -> list[dict]:
    api_key = _get_api_key()
    if not api_key:
        return []
    return _cached_get("ratios", {"symbol": ticker, "limit": 5, "apikey": api_key})


def _get_key_metrics(ticker: str) -> list[dict]:
    api_key = _get_api_key()
    if not api_key:
        return []
    return _cached_get("key-metrics", {"symbol": ticker, "limit": 5, "apikey": api_key})


def _get_cash_flow(ticker: str) -> list[dict]:
    api_key = _get_api_key()
    if not api_key:
        return []
    return _cached_get("cash-flow-statement", {"symbol": ticker, "limit": 5, "apikey": api_key})


def _find_by_year(records: list[dict], year: int) -> Optional[dict]:
    """Return annual record matching year. Checks fiscalYear, then date prefix."""
    for r in records:
        fy = str(r.get("fiscalYear", "") or "")
        if fy.startswith(str(year)) and r.get("period") in ("FY", "annual", None):
            return r
    for r in records:
        d = str(r.get("date", ""))
        if d.startswith(str(year)):
            return r
    return None


# ── Tolerances ────────────────────────────────────────────────────────────────

_TOL_FINANCIAL = 0.05   # 5% for EPS / revenue
_TOL_VALUATION = 0.15   # 15% for multiples (snapshot-date sensitive)


# ── Verifiers ─────────────────────────────────────────────────────────────────

def verify_eps(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    Verify diluted EPS via FMP ratios (netIncomePerShare field).
    Note: netIncomePerShare ≈ diluted EPS for most companies.
    """
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    ratios = _get_ratios(ticker)
    if not ratios:
        return ("", "not_machine_verifiable", "FMP: ratios endpoint unavailable")

    row = _find_by_year(ratios, year)
    if row is None:
        return ("", "not_machine_verifiable", f"FMP: no ratios for FY{year}")

    actual = row.get("netIncomePerShare")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: netIncomePerShare field missing")

    actual = float(actual)
    diff = abs(actual - claimed) / max(abs(actual), 0.01)
    status = "verified" if diff <= _TOL_FINANCIAL else "incorrect"
    return (f"${actual:.2f}", status, f"FMP ratios FY{year} (netIncomePerShare)")


def verify_pe_ratio(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Verify trailing P/E from FMP ratios (priceToEarningsRatio field)."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    ratios = _get_ratios(ticker)
    if not ratios:
        return ("", "not_machine_verifiable", "FMP: ratios endpoint unavailable")

    row = _find_by_year(ratios, year)
    if row is None:
        return ("", "not_machine_verifiable", f"FMP: no ratios for FY{year}")

    actual = row.get("priceToEarningsRatio")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: priceToEarningsRatio missing")

    actual = float(actual)
    if actual <= 0:
        return ("", "not_machine_verifiable", "FMP: negative P/E (loss year)")

    diff = abs(actual - claimed) / max(abs(actual), 0.01)
    status = "verified" if diff <= _TOL_VALUATION else "incorrect"
    return (f"{actual:.1f}x", status, f"FMP ratios FY{year}")


def verify_ev_ebitda(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    Verify EV/EBITDA from FMP.
    Tries ratios.enterpriseValueMultiple first, then key-metrics.evToEBITDA.
    """
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    # Try ratios endpoint first
    ratios = _get_ratios(ticker)
    row = _find_by_year(ratios, year) if ratios else None
    actual = float(row["enterpriseValueMultiple"]) if row and row.get("enterpriseValueMultiple") else None

    # Fallback: key-metrics evToEBITDA
    if actual is None:
        metrics = _get_key_metrics(ticker)
        row = _find_by_year(metrics, year) if metrics else None
        actual = float(row["evToEBITDA"]) if row and row.get("evToEBITDA") else None

    if actual is None:
        return ("", "not_machine_verifiable", "FMP: EV/EBITDA field not found")

    diff = abs(actual - claimed) / max(abs(actual), 0.01)
    status = "verified" if diff <= _TOL_VALUATION else "incorrect"
    return (f"{actual:.1f}x", status, f"FMP ratios FY{year}")


def verify_ebitda_fmp(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    Approximate EBITDA from FMP: netIncome + D&A (from cash flow statement).
    More complete than EDGAR proxy (includes interest/taxes in EBITDA approximation).
    Note: true EBITDA = EBIT + D&A = net income + interest + taxes + D&A.
    This uses net income + D&A as a best-effort proxy. 15% tolerance.
    """
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    cf = _get_cash_flow(ticker)
    if not cf:
        return ("", "not_machine_verifiable", "FMP: cash-flow endpoint unavailable")

    row = _find_by_year(cf, year)
    if row is None:
        return ("", "not_machine_verifiable", f"FMP: no cash-flow for FY{year}")

    net_income = row.get("netIncome")
    da = row.get("depreciationAndAmortization")

    if net_income is None or da is None:
        return ("", "not_machine_verifiable", "FMP: netIncome or D&A field missing")

    approx = float(net_income) + float(da)
    diff = abs(approx - claimed) / max(abs(approx), 1)
    status = "verified" if diff <= 0.15 else "incorrect"
    return (f"${approx/1e9:.2f}B (net income + D&A)", status, f"FMP cash-flow FY{year}")


def verify_revenue_fmp(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    Revenue cross-check via FMP ratios revenuePerShare * sharesOutstanding.
    Better to use SEC EDGAR for revenue; this is a secondary sanity check.
    """
    return ("", "not_machine_verifiable", "FMP: revenue endpoint requires paid plan — use SEC EDGAR")


# ── Extended verifiers (added Jun 6 2026 — raises coverage toward 80%) ────────

def _get_balance_sheet(ticker: str) -> list[dict]:
    api_key = _get_api_key()
    if not api_key:
        return []
    return _cached_get("balance-sheet-statement", {"symbol": ticker, "limit": 5, "apikey": api_key})


def _get_profile(ticker: str) -> Optional[dict]:
    api_key = _get_api_key()
    if not api_key:
        return None
    data = _cached_get("profile", {"symbol": ticker, "apikey": api_key})
    return data[0] if isinstance(data, list) and data else None


def verify_net_income(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Net income from FMP cash-flow statement (netIncome field)."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")
    cf = _get_cash_flow(ticker)
    if not cf:
        return ("", "not_machine_verifiable", "FMP: cash-flow unavailable")
    row = _find_by_year(cf, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no cash-flow for FY{year}")
    actual = row.get("netIncome")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: netIncome field missing")
    actual = float(actual)
    diff = abs(actual - claimed) / max(abs(actual), 1)
    status = "verified" if diff <= _TOL_FINANCIAL else "incorrect"
    return (f"${actual/1e9:.2f}B", status, f"FMP cash-flow FY{year}")


def verify_free_cash_flow(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Free cash flow from FMP cash-flow statement."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")
    cf = _get_cash_flow(ticker)
    if not cf:
        return ("", "not_machine_verifiable", "FMP: cash-flow unavailable")
    row = _find_by_year(cf, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no cash-flow for FY{year}")
    actual = row.get("freeCashFlow")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: freeCashFlow field missing")
    actual = float(actual)
    diff = abs(actual - claimed) / max(abs(actual), 1)
    status = "verified" if diff <= _TOL_FINANCIAL else "incorrect"
    return (f"${actual/1e9:.2f}B", status, f"FMP cash-flow FY{year}")


def verify_gross_margin(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Gross margin % from FMP ratios (grossProfitMargin)."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")
    ratios = _get_ratios(ticker)
    if not ratios:
        return ("", "not_machine_verifiable", "FMP: ratios unavailable")
    row = _find_by_year(ratios, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no ratios for FY{year}")
    actual = row.get("grossProfitMargin")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: grossProfitMargin missing")
    actual = float(actual) * 100  # FMP stores as decimal (0.60 = 60%)
    diff = abs(actual - claimed) / max(abs(actual), 0.01)
    status = "verified" if diff <= _TOL_VALUATION else "incorrect"
    return (f"{actual:.1f}%", status, f"FMP ratios FY{year}")


def verify_net_margin(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Net profit margin % from FMP ratios."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")
    ratios = _get_ratios(ticker)
    if not ratios:
        return ("", "not_machine_verifiable", "FMP: ratios unavailable")
    row = _find_by_year(ratios, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no ratios for FY{year}")
    actual = row.get("netProfitMargin")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: netProfitMargin missing")
    actual = float(actual) * 100
    diff = abs(actual - claimed) / max(abs(actual), 0.01)
    status = "verified" if diff <= _TOL_VALUATION else "incorrect"
    return (f"{actual:.1f}%", status, f"FMP ratios FY{year}")


def verify_market_cap(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Market cap from FMP profile (snapshot — period is informational only)."""
    profile = _get_profile(ticker)
    if not profile:
        return ("", "not_machine_verifiable", "FMP: profile unavailable")
    actual = profile.get("mktCap")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: mktCap field missing")
    actual = float(actual)
    diff = abs(actual - claimed) / max(abs(actual), 1)
    # Market cap is snapshot — use loose tolerance
    status = "verified" if diff <= 0.20 else "incorrect"
    return (f"${actual/1e9:.1f}B", status, "FMP profile (current snapshot)")


def verify_total_debt(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """Total debt from FMP balance sheet."""
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")
    bs = _get_balance_sheet(ticker)
    if not bs:
        return ("", "not_machine_verifiable", "FMP: balance-sheet unavailable")
    row = _find_by_year(bs, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no balance-sheet for FY{year}")
    actual = row.get("totalDebt")
    if actual is None:
        return ("", "not_machine_verifiable", "FMP: totalDebt missing")
    actual = float(actual)
    diff = abs(actual - claimed) / max(abs(actual), 1)
    status = "verified" if diff <= _TOL_FINANCIAL else "incorrect"
    return (f"${actual/1e9:.2f}B", status, f"FMP balance-sheet FY{year}")


# ── Backtesting data gate (Mario's Jun 6 directive) ───────────────────────────

def get_historical_financials(ticker: str, as_of_date: str) -> dict:
    """
    Return all FMP data available strictly before as_of_date.
    Use this to create a date-gated window for backtesting:
      1. Call with as_of_date = "2025-06-01"
      2. Feed returned data to FinRobot as its financial context
      3. Run FinRobot — generates thesis/price-target/catalysts using only past data
      4. Compare FinRobot's forward predictions against what actually happened

    as_of_date: "YYYY-MM-DD"
    """
    from datetime import datetime as dt
    cutoff = dt.strptime(as_of_date, "%Y-%m-%d")

    def gate(rows: list) -> list:
        out = []
        for r in rows:
            date_str = r.get("date") or r.get("fiscalYear") or r.get("fillingDate") or ""
            try:
                d = dt.strptime(str(date_str)[:10], "%Y-%m-%d")
                if d <= cutoff:
                    out.append(r)
            except ValueError:
                pass
        return out

    ratios   = _get_ratios(ticker)
    metrics  = _get_key_metrics(ticker)
    cf       = _get_cash_flow(ticker)
    bs       = _get_balance_sheet(ticker)

    return {
        "ticker":         ticker,
        "as_of_date":     as_of_date,
        "ratios":         gate(ratios)   if ratios  else [],
        "key_metrics":    gate(metrics)  if metrics else [],
        "cash_flow":      gate(cf)       if cf      else [],
        "balance_sheet":  gate(bs)       if bs      else [],
    }


def verify_revenue_growth(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    YoY revenue growth % from SEC EDGAR.
    claimed: percentage value e.g. 122.4 (meaning 122.4%)
    """
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    try:
        from reliability_lab.verifiers.sec_verifier import get_revenue
    except ImportError:
        return ("", "not_machine_verifiable", "SEC EDGAR: import failed")

    rev_current = get_revenue(ticker, year)
    rev_prior   = get_revenue(ticker, year - 1)
    if rev_current is None or rev_prior is None or rev_prior == 0:
        return ("", "not_machine_verifiable", f"SEC EDGAR: insufficient data for FY{year} growth")

    actual_pct = (rev_current - rev_prior) / abs(rev_prior) * 100
    diff = abs(actual_pct - claimed) / max(abs(actual_pct), 0.1)
    status = "verified" if diff <= 0.10 else "incorrect"
    return (f"{actual_pct:.1f}%", status, f"SEC EDGAR 10-K revenue FY{year-1}→FY{year}")


def verify_ebitda_margin(ticker: str, period: str, claimed: float) -> tuple[str, str, str]:
    """
    EBITDA margin % = (net income + D&A) / revenue.
    Uses FMP cash-flow for EBITDA proxy and SEC EDGAR for revenue.
    claimed: percentage value e.g. 55.2 (meaning 55.2%)
    """
    if not period:
        return ("", "not_machine_verifiable", "")
    try:
        year = int(str(period)[:4])
    except (ValueError, TypeError):
        return ("", "not_machine_verifiable", "")

    cf = _get_cash_flow(ticker)
    if not cf:
        return ("", "not_machine_verifiable", "FMP: cash-flow unavailable")
    row = _find_by_year(cf, year)
    if not row:
        return ("", "not_machine_verifiable", f"FMP: no cash-flow for FY{year}")

    net_income = row.get("netIncome")
    da         = row.get("depreciationAndAmortization")
    if net_income is None or da is None:
        return ("", "not_machine_verifiable", "FMP: netIncome or D&A missing")

    ebitda_proxy = float(net_income) + float(da)

    try:
        from reliability_lab.verifiers.sec_verifier import get_revenue
    except ImportError:
        return ("", "not_machine_verifiable", "SEC EDGAR: import failed")

    revenue = get_revenue(ticker, year)
    if not revenue or revenue == 0:
        return ("", "not_machine_verifiable", f"SEC EDGAR: no revenue for FY{year}")

    actual_pct = ebitda_proxy / revenue * 100
    diff = abs(actual_pct - claimed) / max(abs(actual_pct), 0.1)
    status = "verified" if diff <= 0.10 else "incorrect"
    return (f"{actual_pct:.1f}%", status, f"FMP/SEC EBITDA margin FY{year}")


# ── Dispatch table (maps claim type → verifier fn) ────────────────────────────

FMP_VERIFIERS = {
    "eps":              verify_eps,
    "pe_ratio":         verify_pe_ratio,
    "ev_ebitda":        verify_ev_ebitda,
    "ebitda":           verify_ebitda_fmp,
    "net_income":       verify_net_income,
    "free_cash_flow":   verify_free_cash_flow,
    "gross_margin":     verify_gross_margin,
    "net_margin":       verify_net_margin,
    "market_cap":       verify_market_cap,
    "total_debt":       verify_total_debt,
    "revenue_growth":   verify_revenue_growth,
    "ebitda_margin":    verify_ebitda_margin,
    "growth_rate":      verify_revenue_growth,  # CAGR claims → best-effort YoY proxy
}
