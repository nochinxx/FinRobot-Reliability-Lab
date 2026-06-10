#!/usr/bin/env python3
"""
Merge per-ticker fact tables into output/master_fact_table.csv.

Usage:
  python run_master_fact_table.py                        # all tickers with output/ dirs
  python run_master_fact_table.py --tickers NVDA TSLA    # specific tickers
  python run_master_fact_table.py --output-dir my_out/   # custom output directory
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reliability_lab.master_fact_table import (
    merge_fact_tables,
    save_master_fact_table,
    status_summary,
)

_DEFAULT_OUTPUT = "output"
_ALL_TICKERS = [
    "COP", "MSFT", "META", "NVDA", "TSLA",
    "ETSY", "ROKU", "RIVN", "RBLX", "LCID",
]


def _discover_tickers(base_dir: str) -> list[str]:
    """Find tickers that have a fact table CSV in base_dir."""
    base = Path(base_dir)
    found = []
    for child in sorted(base.iterdir()):
        if child.is_dir():
            csv = child / f"{child.name}_fact_table.csv"
            if csv.exists():
                found.append(child.name)
    return found


def main():
    parser = argparse.ArgumentParser(description="Merge per-ticker fact tables into master CSV")
    parser.add_argument("--tickers", nargs="+", metavar="TICKER",
                        help="Tickers to merge (default: auto-discover from output/)")
    parser.add_argument("--output-dir", default=_DEFAULT_OUTPUT,
                        help=f"Base output directory (default: {_DEFAULT_OUTPUT})")
    args = parser.parse_args()

    base = args.output_dir
    tickers = [t.upper() for t in args.tickers] if args.tickers else _discover_tickers(base)

    if not tickers:
        print(f"No fact tables found in {base}/ — run reliability audits first.")
        return 1

    print(f"Merging fact tables for: {', '.join(tickers)}")
    merged = merge_fact_tables(tickers, base_output_dir=base)

    if not merged:
        print("No rows merged — check that fact table CSVs exist.")
        return 1

    out_path = save_master_fact_table(merged, output_dir=base)
    summary = status_summary(merged)

    print(f"\n{'━'*50}")
    print(f"  Master Fact Table: {out_path}")
    print(f"{'━'*50}")
    print(f"  Total rows:   {summary['total']}")
    print(f"  LOCKED:       {summary['LOCKED']}  (verified Tier 1 / SEC EDGAR)")
    print(f"  PROVISIONAL:  {summary['PROVISIONAL']}  (verified Tier 3 / FMP only)")
    print(f"  CONFLICT:     {summary['CONFLICT']}  (Tier 1 ≠ Tier 3 beyond tolerance)")
    print(f"  INCORRECT:    {summary['INCORRECT']}  (confirmed wrong)")
    print(f"  UNVERIFIED:   {summary['UNVERIFIED']}  (unsupported / NMV)")
    print(f"{'━'*50}")

    if summary['LOCKED'] > 0:
        locked_pct = 100 * summary['LOCKED'] / summary['total']
        print(f"  Coverage (LOCKED+PROVISIONAL): "
              f"{100*(summary['LOCKED']+summary['PROVISIONAL'])/summary['total']:.1f}%")
        print(f"  Tier 1 locked: {locked_pct:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
