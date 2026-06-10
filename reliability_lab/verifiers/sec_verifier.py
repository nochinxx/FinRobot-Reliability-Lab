"""
Verify financial claims against SEC filings using the SEC EDGAR API.
Free, no API key needed.

Day 5 sprint target.

SEC EDGAR company facts API:
  https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json
"""
import json
import re
import urllib.request
from typing import Optional

from reliability_lab.verifiers.api_cache import sec_get


EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2024-01-01&forms=10-K,10-Q"
EDGAR_FACTS  = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
EDGAR_TICKER = "https://www.sec.gov/files/company_tickers.json"

_ticker_to_cik: dict = {}


def _load_ticker_map() -> dict:
    global _ticker_to_cik
    if _ticker_to_cik:
        return _ticker_to_cik
    req = urllib.request.Request(EDGAR_TICKER, headers={"User-Agent": "FinRobot-ReliabilityLab research@example.com"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
    for v in data.values():
        _ticker_to_cik[v["ticker"].upper()] = str(v["cik_str"]).zfill(10)
    return _ticker_to_cik


def get_cik(ticker: str) -> Optional[str]:
    m = _load_ticker_map()
    return m.get(ticker.upper())


def get_company_facts(ticker: str) -> Optional[dict]:
    """Fetch company facts from SEC EDGAR with 7-day persistent cache."""
    cik = get_cik(ticker)
    if not cik:
        return None

    def _fetch():
        url = EDGAR_FACTS.format(cik=cik)
        req = urllib.request.Request(url, headers={"User-Agent": "FinRobot-ReliabilityLab research@example.com"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())

    return sec_get(cik, _fetch)


def get_revenue(ticker: str, year: int) -> Optional[float]:
    """
    Fetch annual revenue from SEC EDGAR for the given fiscal year.
    Returns value in USD (raw, not millions).
    """
    facts = get_company_facts(ticker)
    if not facts:
        return None
    # US-GAAP revenue concepts in order of preference
    for concept in ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]:
        try:
            units = facts["facts"]["us-gaap"][concept]["units"]["USD"]
            annual = [u for u in units if u.get("form") in ("10-K",) and u.get("fp") == "FY"]
            for entry in reversed(annual):
                if entry.get("end", "").startswith(str(year)):
                    return float(entry["val"])
        except (KeyError, TypeError):
            continue
    return None
