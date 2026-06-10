"""
Cache Manager — inspect, warm, and export the API response cache.

Commands:
  --status              Show all cached entries (age, size, stale flag)
  --warm NVDA TSLA …   Fetch all FMP + SEC endpoints for given tickers
  --warm --all          Warm all 10 Phase 1+2 tickers
  --export              Copy cache to tests/fixtures/api_responses/ (for offline tests)
  --purge NVDA          Delete all cache entries for a ticker (force re-fetch next run)
  --purge --all         Delete all cache entries

None of the warm commands count against your 250/day FMP quota if the data is already cached.
Stale entries (>24h for FMP, >7d for SEC) are refetched automatically.

Usage:
  conda run -n agent python tools/cache_manager.py --status
  conda run -n agent python tools/cache_manager.py --warm NVDA
  conda run -n agent python tools/cache_manager.py --warm --all
  conda run -n agent python tools/cache_manager.py --export
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

ALL_TICKERS = ["COP", "MSFT", "META", "NVDA", "TSLA", "ETSY", "ROKU", "RIVN", "RBLX", "LCID"]


def cmd_status():
    from reliability_lab.verifiers.api_cache import cache_status, _CACHE_ROOT
    status = cache_status()
    if not status:
        print(f"Cache is empty. Root: {_CACHE_ROOT}")
        return
    total_size = 0
    total_entries = 0
    stale_count = 0
    for ns, entries in sorted(status.items()):
        print(f"\n[{ns.upper()}]")
        for key, info in sorted(entries.items()):
            age = info["age_hours"]
            size = info["size_kb"]
            flag = " STALE" if info["stale"] else ""
            print(f"  {key:<50s}  {age:5.1f}h  {size:6.1f}KB{flag}")
            total_size += size
            total_entries += 1
            if info["stale"]:
                stale_count += 1
    print(f"\nTotal: {total_entries} entries, {total_size:.1f}KB, {stale_count} stale")


def _warm_ticker(ticker: str):
    """Fetch all FMP endpoints + SEC EDGAR for one ticker. Respects existing fresh cache."""
    from reliability_lab.verifiers.fmp_verifier import (
        _get_ratios, _get_key_metrics, _get_cash_flow,
        _get_balance_sheet, _get_profile
    )
    from reliability_lab.verifiers.sec_verifier import get_company_facts

    endpoints = {
        "ratios":          lambda: _get_ratios(ticker),
        "key-metrics":     lambda: _get_key_metrics(ticker),
        "cash-flow":       lambda: _get_cash_flow(ticker),
        "balance-sheet":   lambda: _get_balance_sheet(ticker),
        "profile":         lambda: _get_profile(ticker),
        "SEC company_facts": lambda: get_company_facts(ticker),
    }
    results = {}
    for name, fn in endpoints.items():
        try:
            data = fn()
            if data:
                rows = len(data) if isinstance(data, list) else 1
                results[name] = f"ok ({rows} rows)"
            else:
                results[name] = "empty / not_available"
        except Exception as e:
            results[name] = f"ERROR: {e}"
    return results


def cmd_warm(tickers: list[str]):
    print(f"Warming cache for {len(tickers)} ticker(s)...")
    for ticker in tickers:
        print(f"\n  {ticker}:")
        results = _warm_ticker(ticker)
        for ep, status in results.items():
            print(f"    {ep:<25s} {status}")
    print("\nDone.")


def cmd_export():
    """Copy all cache files to tests/fixtures/api_responses/ for offline test use."""
    from reliability_lab.verifiers.api_cache import _CACHE_ROOT
    dest = REPO / "tests" / "fixtures" / "api_responses"
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for ns_dir in _CACHE_ROOT.iterdir():
        if not ns_dir.is_dir():
            continue
        ns_dest = dest / ns_dir.name
        ns_dest.mkdir(exist_ok=True)
        for f in ns_dir.glob("*.json"):
            target = ns_dest / f.name
            target.write_bytes(f.read_bytes())
            copied += 1
    print(f"Exported {copied} cache files to {dest}")


def cmd_purge(tickers: list[str], purge_all: bool):
    from reliability_lab.verifiers.api_cache import _CACHE_ROOT
    deleted = 0
    for ns_dir in _CACHE_ROOT.iterdir():
        if not ns_dir.is_dir():
            continue
        for f in ns_dir.glob("*.json"):
            if purge_all or any(t.upper() in f.stem.upper() for t in tickers):
                f.unlink()
                deleted += 1
                print(f"  Deleted: {ns_dir.name}/{f.name}")
    print(f"\nPurged {deleted} cache files.")


def main():
    parser = argparse.ArgumentParser(description="FinRobot API Cache Manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    status_p = sub.add_parser("status", help="Show cache status")

    warm_p = sub.add_parser("warm", help="Warm cache for tickers")
    warm_p.add_argument("tickers", nargs="*", help="Ticker symbols")
    warm_p.add_argument("--all", action="store_true", help="Warm all 10 tickers")

    export_p = sub.add_parser("export", help="Export cache to tests/fixtures/api_responses/")

    purge_p = sub.add_parser("purge", help="Delete cache entries")
    purge_p.add_argument("tickers", nargs="*", help="Ticker symbols")
    purge_p.add_argument("--all", action="store_true", help="Purge all entries")

    args = parser.parse_args()

    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "warm":
        tickers = ALL_TICKERS if args.all else [t.upper() for t in args.tickers]
        if not tickers:
            parser.error("Specify tickers or --all")
        cmd_warm(tickers)
    elif args.cmd == "export":
        cmd_export()
    elif args.cmd == "purge":
        if not args.tickers and not args.all:
            parser.error("Specify tickers or --all")
        cmd_purge([t.upper() for t in args.tickers], args.all)


if __name__ == "__main__":
    main()
