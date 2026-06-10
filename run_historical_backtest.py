#!/usr/bin/env python3
"""
run_historical_backtest.py — Historical date-gated backtesting.

For each (ticker, cutoff_date) pair:
  1. Fetch FMP financial data available strictly before cutoff_date
  2. Compute a simple valuation signal using only that historical data
  3. Get actual stock price at cutoff_date via yfinance
  4. Measure forward returns at +3m, +6m, +9m, +12m vs. SPY

This answers Mario's question: "feed it with that data to get some theses
with catalysts and then check over the periods of time forward if the
predictions were accurate or not."

Usage:
    conda run -n agent python run_historical_backtest.py
    conda run -n agent python run_historical_backtest.py --ticker NVDA TSLA
    conda run -n agent python run_historical_backtest.py --cutoff 2025-06-01 2025-09-01

Outputs:
    output/historical_backtest/results.csv
    output/historical_backtest/paper_table.md
    output/historical_backtest/<TICKER>_<DATE>_snapshot.json
"""

import argparse
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
    YFINANCE = True
except ImportError:
    YFINANCE = False
    print("[WARN] yfinance not installed — run: conda run -n agent pip install yfinance")

from reliability_lab.verifiers.fmp_verifier import get_historical_financials

OUTPUT_DIR = Path("output/historical_backtest")

# Default tickers and cutoff dates for backtesting
DEFAULT_TICKERS = ["NVDA", "TSLA", "META", "MSFT", "COP"]

# Three windows: 12m, 9m, 6m ago from Jun 2026
DEFAULT_CUTOFFS = [
    "2025-06-01",  # T-12m: full 12-month return available
    "2025-09-01",  # T-9m: 9-month return available
    "2025-12-01",  # T-6m: 6-month return available
]


def compute_valuation_signal(financials: dict) -> dict:
    """
    Compute simple valuation signal from historical FMP data.

    Signal logic:
      - Use trailing P/E and EV/EBITDA from available annual records
      - If EV/EBITDA < sector rough threshold (30x for tech, 15x for energy),
        or P/E < historical mean for that ticker → signal = "undervalued"
      - If EV/EBITDA > threshold * 1.5 → "overvalued"
      - Otherwise → "fairly valued"

    Returns dict with: pe_ratio, ev_ebitda, signal, rationale
    """
    ratios   = financials.get("ratios", [])
    metrics  = financials.get("key_metrics", [])

    # Get most recent annual record available
    most_recent_ratio  = ratios[0]  if ratios  else {}
    most_recent_metric = metrics[0] if metrics else {}

    pe   = most_recent_ratio.get("priceToEarningsRatio")
    evm  = most_recent_ratio.get("enterpriseValueMultiple") or most_recent_metric.get("evToEBITDA")
    npm  = most_recent_ratio.get("netProfitMargin")
    gpm  = most_recent_ratio.get("grossProfitMargin")

    # Historical mean P/E (using all available records)
    pe_history = [
        float(r["priceToEarningsRatio"])
        for r in ratios
        if r.get("priceToEarningsRatio") and float(r["priceToEarningsRatio"]) > 0
    ]
    ev_history = [
        float(r["enterpriseValueMultiple"])
        for r in ratios
        if r.get("enterpriseValueMultiple") and float(r["enterpriseValueMultiple"]) > 0
    ]

    mean_pe = statistics.mean(pe_history) if len(pe_history) >= 2 else None
    mean_ev = statistics.mean(ev_history) if len(ev_history) >= 2 else None

    # Signal: compare current multiple to historical mean
    signal = "hold"
    rationale_parts = []

    if pe and mean_pe and pe > 0:
        pe = float(pe)
        premium_pe = (pe - mean_pe) / mean_pe
        if premium_pe < -0.15:
            signal = "buy"
            rationale_parts.append(f"P/E {pe:.1f}x is {abs(premium_pe)*100:.0f}% below historical mean {mean_pe:.1f}x")
        elif premium_pe > 0.30:
            signal = "sell" if signal != "buy" else "hold"
            rationale_parts.append(f"P/E {pe:.1f}x is {premium_pe*100:.0f}% above historical mean {mean_pe:.1f}x")
        else:
            rationale_parts.append(f"P/E {pe:.1f}x near historical mean {mean_pe:.1f}x")

    if evm and mean_ev and float(evm) > 0:
        evm = float(evm)
        premium_ev = (evm - mean_ev) / mean_ev
        if premium_ev < -0.15:
            signal = "buy"
            rationale_parts.append(f"EV/EBITDA {evm:.1f}x below historical mean {mean_ev:.1f}x")
        elif premium_ev > 0.30:
            if signal != "buy":
                signal = "sell"
            rationale_parts.append(f"EV/EBITDA {evm:.1f}x above historical mean {mean_ev:.1f}x")
        else:
            rationale_parts.append(f"EV/EBITDA {evm:.1f}x near mean {mean_ev:.1f}x")

    if not rationale_parts:
        rationale_parts.append("Insufficient ratio history — hold")

    # Profitability score (0-10, used as a tiebreaker)
    profit_score = 0
    if npm and float(npm) > 0.20:
        profit_score += 3
    elif npm and float(npm) > 0.10:
        profit_score += 1
    if gpm and float(gpm) > 0.60:
        profit_score += 3
    elif gpm and float(gpm) > 0.40:
        profit_score += 1

    return {
        "pe_ratio": round(float(pe), 2) if pe else None,
        "ev_ebitda": round(float(evm), 2) if evm else None,
        "mean_pe_history": round(mean_pe, 2) if mean_pe else None,
        "mean_ev_history": round(mean_ev, 2) if mean_ev else None,
        "net_profit_margin": round(float(npm) * 100, 1) if npm else None,
        "gross_profit_margin": round(float(gpm) * 100, 1) if gpm else None,
        "profitability_score": profit_score,
        "signal": signal,
        "rationale": " | ".join(rationale_parts),
        "ratio_history_depth": len(pe_history),
    }


def get_price_at_date(ticker: str, target_date: str) -> float | None:
    """Get closing price closest to target_date from yfinance."""
    if not YFINANCE:
        return None
    try:
        start = (datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        end   = (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
        hist = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if hist.empty:
            return None
        close = hist["Close"]
        if hasattr(close, "columns"):
            close = close.squeeze()
        return float(close.iloc[-1])
    except Exception as e:
        print(f"  [price] yfinance error for {ticker} at {target_date}: {e}")
        return None


def get_forward_return(ticker: str, start_date: str, months: int) -> float | None:
    """Get % return from start_date + months months."""
    if not YFINANCE:
        return None
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end   = start + timedelta(days=int(months * 30.5))
        if end > datetime.now():
            return None
        hist = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=10)).strftime("%Y-%m-%d"),
            progress=False, auto_adjust=True,
        )
        if hist.empty:
            return None
        close = hist["Close"]
        if hasattr(close, "columns"):
            close = close.squeeze()
        buy_price  = float(close.iloc[0])
        idx = close.index.searchsorted(pd.Timestamp(end.strftime("%Y-%m-%d")))
        if idx >= len(close):
            idx = len(close) - 1
        sell_price = float(close.iloc[idx])
        return round((sell_price - buy_price) / buy_price * 100, 2)
    except Exception as e:
        print(f"  [return] yfinance error for {ticker}: {e}")
        return None


def run_window(ticker: str, cutoff_date: str) -> dict | None:
    """Run one (ticker, cutoff_date) backtesting window."""
    print(f"  [{ticker} @ {cutoff_date}] Fetching historical financials...")

    financials = get_historical_financials(ticker, cutoff_date)
    ratios  = financials.get("ratios", [])
    cf      = financials.get("cash_flow", [])
    bs      = financials.get("balance_sheet", [])

    if not ratios:
        print(f"  [{ticker} @ {cutoff_date}] No FMP ratio data — skipping")
        return None

    valuation = compute_valuation_signal(financials)
    print(f"  [{ticker} @ {cutoff_date}] Signal: {valuation['signal']} | {valuation['rationale'][:80]}")

    # Get price at cutoff date
    price_at_cutoff = get_price_at_date(ticker, cutoff_date)
    if price_at_cutoff is None:
        print(f"  [{ticker} @ {cutoff_date}] Could not get price — skipping")
        return None

    print(f"  [{ticker} @ {cutoff_date}] Price: ${price_at_cutoff:.2f}")

    # Get forward returns (3m, 6m, 9m, 12m)
    returns = {}
    spy_returns = {}
    for months in [3, 6, 9, 12]:
        r   = get_forward_return(ticker, cutoff_date, months)
        spy = get_forward_return("SPY", cutoff_date, months)
        returns[f"return_{months}m"]     = r
        spy_returns[f"spy_{months}m"]    = spy
        if r is not None:
            alpha = round(r - (spy or 0), 2) if spy is not None else None
            returns[f"alpha_{months}m"] = alpha
            print(f"  [{ticker} @ {cutoff_date}] Return {months}m: {r:.1f}% | SPY: {spy:.1f}% | Alpha: {alpha:.1f}%")
        else:
            returns[f"alpha_{months}m"] = None

    # Save snapshot
    snapshot = {
        "ticker":         ticker,
        "cutoff_date":    cutoff_date,
        "price_at_cutoff": price_at_cutoff,
        "valuation":      valuation,
        "fmp_records": {
            "ratios": len(ratios),
            "cash_flow": len(cf),
            "balance_sheet": len(bs),
        },
        "returns":        returns,
        "spy_returns":    spy_returns,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = OUTPUT_DIR / f"{ticker}_{cutoff_date[:7]}_snapshot.json"
    snap_path.write_text(json.dumps(snapshot, indent=2))

    row = {
        "ticker":          ticker,
        "cutoff_date":     cutoff_date,
        "price_at_cutoff": round(price_at_cutoff, 2),
        "signal":          valuation["signal"],
        "pe_ratio":        valuation["pe_ratio"],
        "ev_ebitda":       valuation["ev_ebitda"],
        "mean_pe":         valuation["mean_pe_history"],
        "net_margin_pct":  valuation["net_profit_margin"],
        "profitability":   valuation["profitability_score"],
        **returns,
        **spy_returns,
    }
    return row


def save_results(results: list[dict]):
    if not results:
        print("[hist_backtest] No results")
        return

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_DIR / "results.csv", index=False)
    print(f"\n[hist_backtest] Results → {OUTPUT_DIR}/results.csv")

    # Paper table
    key_cols = [
        "ticker", "cutoff_date", "signal", "pe_ratio", "ev_ebitda",
        "return_3m", "alpha_3m", "return_6m", "alpha_6m",
        "return_9m", "alpha_9m", "return_12m", "alpha_12m",
    ]
    available = [c for c in key_cols if c in df.columns]

    with open(OUTPUT_DIR / "paper_table.md", "w") as f:
        f.write("# Historical Backtest Results — Date-Gated Signal Quality\n\n")
        f.write(df[available].to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n*Signal generated using only FMP data available before cutoff_date.*\n")
        f.write("*Alpha = stock return minus SPY return over same period.*\n\n")

        # Summary stats by signal
        f.write("## Signal Performance Summary\n\n")
        for sig in ["buy", "hold", "sell"]:
            subset = df[df["signal"] == sig]
            if subset.empty:
                continue
            f.write(f"### {sig.upper()} signals ({len(subset)} observations)\n")
            for horizon in ["return_3m", "return_6m", "return_9m", "return_12m",
                            "alpha_3m", "alpha_6m", "alpha_9m", "alpha_12m"]:
                if horizon in df.columns:
                    vals = subset[horizon].dropna()
                    if not vals.empty:
                        f.write(f"  {horizon}: mean={vals.mean():.1f}%, median={vals.median():.1f}%\n")
            f.write("\n")

    print(f"[hist_backtest] Paper table → {OUTPUT_DIR}/paper_table.md")

    # Print summary
    buy_sigs = df[df["signal"] == "buy"]
    if not buy_sigs.empty:
        print("\n[hist_backtest] BUY signal performance:")
        for h in ["return_3m", "return_6m", "alpha_3m", "alpha_6m"]:
            if h in df.columns:
                vals = buy_sigs[h].dropna()
                if not vals.empty:
                    print(f"  {h}: mean {vals.mean():.1f}%, n={len(vals)}")


def main():
    parser = argparse.ArgumentParser(description="Historical date-gated backtesting")
    parser.add_argument("--ticker", nargs="*", default=DEFAULT_TICKERS,
                        help="Tickers to backtest")
    parser.add_argument("--cutoff", nargs="*", default=DEFAULT_CUTOFFS,
                        help="Cutoff dates (YYYY-MM-DD)")
    parser.add_argument("--ticker-all", action="store_true",
                        help="Use all audited tickers")
    args = parser.parse_args()

    if args.ticker_all:
        audit_dir = Path("output")
        tickers = [d.name for d in audit_dir.iterdir()
                   if d.is_dir() and (d / f"{d.name}_reliability_scorecard.json").exists()
                   and d.name != "historical_backtest"]
    else:
        tickers = [t.upper() for t in args.ticker]

    cutoffs = args.cutoff
    print(f"[hist_backtest] Tickers: {tickers}")
    print(f"[hist_backtest] Cutoff dates: {cutoffs}")
    print(f"[hist_backtest] Total runs: {len(tickers) * len(cutoffs)}\n")

    results = []
    for ticker in tickers:
        for cutoff in cutoffs:
            print(f"\n{'─'*50}")
            r = run_window(ticker, cutoff)
            if r:
                results.append(r)

    print(f"\n{'─'*50}")
    save_results(results)


if __name__ == "__main__":
    main()
