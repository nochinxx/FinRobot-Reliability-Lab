"""
Verify stock return, drawdown, and relative performance claims
using yfinance (free, no API key needed).

Day 4 sprint target.
"""
from datetime import datetime, timedelta
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_return(ticker: str, start: str, end: str) -> Optional[float]:
    """
    Return total return (as decimal) for ticker between start and end dates.
    Dates as 'YYYY-MM-DD'.
    """
    if yf is None:
        raise ImportError("yfinance not installed: conda run -n agent pip install yfinance")
    data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if data.empty:
        return None
    start_price = float(data["Close"].iloc[0])
    end_price = float(data["Close"].iloc[-1])
    return (end_price - start_price) / start_price


def verify_return_claim(ticker: str, period_start: str, period_end: str, claimed_return: float,
                        tolerance: float = 0.02) -> dict:
    """
    Compare claimed return against actual. Returns verification result dict.
    tolerance: acceptable absolute difference (default 2%).
    """
    actual = get_return(ticker, period_start, period_end)
    if actual is None:
        return {"status": "not_machine_verifiable", "reason": "no price data"}

    diff = abs(actual - claimed_return)
    status = "verified" if diff <= tolerance else "incorrect"
    return {
        "status": status,
        "claimed": claimed_return,
        "actual": round(actual, 4),
        "diff": round(diff, 4),
    }
