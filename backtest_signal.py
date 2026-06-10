"""
backtest_signal.py — Signal quality after verification

For each audited stock:
1. Extract FinRobot's target price + report date from claims
2. Get actual price history via yfinance
3. Compute return at T+6m and T+1y vs. SPY benchmark
4. Correlate signal quality (ICR, SCR, VD) with realized alpha

Usage:
    conda run -n agent python backtest_signal.py --all
    conda run -n agent python backtest_signal.py --ticker NVDA
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
    YFINANCE = True
except ImportError:
    YFINANCE = False
    print("[WARN] yfinance not available — install with: conda run -n agent pip install yfinance")

OUTPUT_DIR = Path("output")
RESULTS_FILE = Path("output/backtest_results.csv")
PAPER_TABLE_FILE = Path("output/backtest_paper_table.md")


def extract_signal(ticker: str) -> dict | None:
    """Extract target price, current price, report date from claims.json."""
    claims_path = OUTPUT_DIR / ticker / f"{ticker}_claims.json"
    scorecard_path = OUTPUT_DIR / ticker / f"{ticker}_reliability_scorecard.json"

    if not claims_path.exists() or not scorecard_path.exists():
        print(f"[{ticker}] Missing claims or scorecard — run audit first")
        return None

    with open(claims_path) as f:
        claims = json.load(f)

    with open(scorecard_path) as f:
        scorecard = json.load(f)

    # Look for target price in valuation claims
    target_price = None
    current_price = None
    report_date = None

    for claim in claims:
        text = claim.get("claim_text", "")
        # Pattern: "Target $NNN.NN"
        if target_price is None:
            m = re.search(r"Target\s+\$?([\d,]+\.?\d*)", text)
            if m:
                target_price = float(m.group(1).replace(",", ""))
        # Pattern: "Price $NNN.NN" (current price at report time)
        if current_price is None:
            m = re.search(r"Price\s+\$?([\d,]+\.?\d*)", text)
            if m:
                current_price = float(m.group(1).replace(",", ""))
        # Date pattern: "Month DD, YYYY" or "YYYY-MM-DD"
        if report_date is None:
            m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}", text)
            if m:
                try:
                    report_date = datetime.strptime(m.group(0), "%B %d, %Y")
                except ValueError:
                    pass

    if target_price is None or current_price is None or current_price == 0:
        print(f"[{ticker}] Could not extract target/current price from claims")
        return None

    # If no date found in claims, use file mtime as fallback
    if report_date is None:
        mtime = claims_path.stat().st_mtime
        report_date = datetime.fromtimestamp(mtime)
        print(f"[{ticker}] Using file mtime as report date: {report_date.date()}")

    metrics = scorecard.get("metrics", {})
    return {
        "ticker": ticker,
        "report_date": report_date.strftime("%Y-%m-%d"),
        "current_price": current_price,
        "target_price": target_price,
        "upside_pct": (target_price - current_price) / current_price * 100,
        "signal": "buy" if target_price > current_price * 1.05 else "hold",
        "icr": metrics.get("incorrect_claim_rate", None),
        "scr": metrics.get("source_coverage_rate", None),
        "vd": metrics.get("valuation_dispersion", None),
    }


def get_returns(ticker: str, start_date: str) -> dict:
    """Get realized price returns at current, +6m and +1y from start_date."""
    if not YFINANCE:
        return {"return_current": None, "return_6m": None, "return_1y": None,
                "spy_return_6m": None, "spy_return_1y": None}

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end_6m = start + timedelta(days=182)
    end_1y = start + timedelta(days=365)
    end_fetch = min(end_1y + timedelta(days=5), datetime.now())

    results = {}
    for sym in [ticker, "SPY"]:
        try:
            hist = yf.download(sym, start=start.strftime("%Y-%m-%d"), end=end_fetch.strftime("%Y-%m-%d"),
                               progress=False, auto_adjust=True)
            if hist.empty:
                results[sym] = None
                continue

            # Close prices by date — handle MultiIndex columns in newer yfinance
            close_col = hist["Close"]
            if hasattr(close_col, "columns"):
                # DataFrame (multi-ticker or new yfinance format) — squeeze to Series
                close_col = close_col.squeeze()
                if hasattr(close_col, "columns"):
                    close_col = close_col.iloc[:, 0]
            closes = close_col.dropna()
            buy_price = float(closes.iloc[0])

            def return_at(target_date: datetime):
                target_str = target_date.strftime("%Y-%m-%d")
                # Find closest available date
                idx = closes.index.searchsorted(pd.Timestamp(target_str))
                if idx >= len(closes):
                    idx = len(closes) - 1
                sell_price = float(closes.iloc[idx])
                return (sell_price - buy_price) / buy_price * 100

            now = datetime.now()
            results[sym] = {
                "return_current": return_at(now - timedelta(days=1)),
                "return_6m": return_at(end_6m) if end_6m <= now else None,
                "return_1y": return_at(end_1y) if end_1y <= now else None,
            }
        except Exception as e:
            print(f"[{ticker}] yfinance error for {sym}: {e}")
            results[sym] = None

    ticker_r = results.get(ticker) or {}
    spy_r = results.get("SPY") or {}

    def alpha(t_key, s_key):
        tv = ticker_r.get(t_key)
        sv = spy_r.get(s_key)
        return round((tv or 0) - (sv or 0), 2) if tv is not None else None

    return {
        "return_current": ticker_r.get("return_current"),
        "spy_return_current": spy_r.get("return_current"),
        "alpha_current": alpha("return_current", "return_current"),
        "return_6m": ticker_r.get("return_6m"),
        "return_1y": ticker_r.get("return_1y"),
        "spy_return_6m": spy_r.get("return_6m"),
        "spy_return_1y": spy_r.get("return_1y"),
        "alpha_6m": alpha("return_6m", "return_6m"),
        "alpha_1y": alpha("return_1y", "return_1y"),
    }


def run_backtest(ticker: str) -> dict | None:
    signal = extract_signal(ticker)
    if signal is None:
        return None

    print(f"[{ticker}] Signal: {signal['signal']} | Upside: {signal['upside_pct']:.1f}% | ICR: {signal['icr']} | SCR: {signal['scr']}")

    returns = get_returns(ticker, signal["report_date"])
    result = {**signal, **returns}

    print(f"[{ticker}] Return 6m: {returns.get('return_6m'):.1f}%" if returns.get("return_6m") is not None else f"[{ticker}] Return 6m: N/A (future)")
    print(f"[{ticker}] Alpha 1y:  {returns.get('alpha_1y'):.1f}%" if returns.get("alpha_1y") is not None else f"[{ticker}] Alpha 1y: N/A (future)")

    return result


def save_results(results: list[dict]):
    if not results:
        print("[backtest] No results to save")
        return

    df = pd.DataFrame(results)
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    df.to_csv(RESULTS_FILE, index=False)
    print(f"\n[backtest] Results saved to {RESULTS_FILE}")

    # Paper-ready markdown table
    cols = ["ticker", "report_date", "upside_pct", "icr", "scr", "vd",
            "return_current", "alpha_current", "return_6m", "return_1y",
            "alpha_6m", "alpha_1y", "signal"]
    available = [c for c in cols if c in df.columns]
    with open(PAPER_TABLE_FILE, "w") as f:
        f.write("# Backtest Results — Signal Quality After Verification\n\n")
        f.write(df[available].to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n*ICR = Incorrect Claim Rate, SCR = Source Coverage Rate, VD = Valuation Dispersion*\n")
        f.write("*Alpha = stock return minus SPY return over same period*\n")
    print(f"[backtest] Paper table saved to {PAPER_TABLE_FILE}")

    # Summary stats
    verified_signals = df[df["icr"].notna() & (df["icr"] < 0.10)]
    if not verified_signals.empty and "alpha_1y" in df.columns:
        valid = verified_signals["alpha_1y"].dropna()
        if not valid.empty:
            print(f"\n[backtest] Verified signals (ICR<0.10) avg alpha 1y: {valid.mean():.1f}%")

    all_signals = df[df["alpha_1y"].notna()]
    if not all_signals.empty:
        print(f"[backtest] All signals avg alpha 1y: {all_signals['alpha_1y'].mean():.1f}%")


def get_available_tickers() -> list[str]:
    return [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / f"{d.name}_reliability_scorecard.json").exists()]


def main():
    parser = argparse.ArgumentParser(description="Backtest FinRobot signals vs. actual returns")
    parser.add_argument("--ticker", type=str, help="Single ticker to backtest")
    parser.add_argument("--all", action="store_true", help="Run all available tickers")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.all:
        tickers = get_available_tickers()
        print(f"[backtest] Found {len(tickers)} audited tickers: {tickers}")
    else:
        parser.print_help()
        return

    results = []
    for ticker in tickers:
        r = run_backtest(ticker)
        if r:
            results.append(r)

    save_results(results)


if __name__ == "__main__":
    main()
