"""
HTML Table Parser — Proof of Value (PR1)

Extracts structured tables from FinRobot HTML equity reports, preserving the
year-column / metric-row structure that _strip_html() destroys.

NOTE: The core parsing functions (parse_report, _normalize_value) are imported
by reliability_lab/ingestion/html_tables.py as of PR3 (Mario approved 2026-06-09).
This CLI remains for standalone PoV runs.

Usage (CLI):
    conda run -n agent python tools/html_table_parser.py --ticker NVDA
    conda run -n agent python tools/html_table_parser.py --all

Output:
    output/table_parse_preview/{TICKER}_tables.json

Each output file is a list of table objects:
  {
    "table_id":    str | null,    # HTML id attribute if present
    "table_index": int,           # 0-based position in document
    "columns":     [str],         # header row values
    "rows": [
      {
        "metric":  str,           # first column (row label)
        "cells": [
          {
            "period":           str | null,   # year/period from column header
            "raw_value":        str,          # value as it appears in HTML
            "normalized_value": float | null, # numeric value, base units
            "unit":             str           # "USD", "percent", "multiple", "text"
          }
        ]
      }
    ],
    "period_columns": [str],      # subset of columns that look like years/periods
    "year_value_pairs": [         # flat list of (metric, period, value) for quick audit
      {"metric": str, "period": str, "raw_value": str, "normalized_value": float|null, "unit": str}
    ]
  }
"""
import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

REPO = Path(__file__).parent.parent
REPORT_DIR = REPO / "finrobot_equity" / "core" / "output"
OUTPUT_DIR = REPO / "output" / "table_parse_preview"

# Patterns for value normalization
_DOLLAR_BIG = re.compile(r'^\$?([\d,]+(?:\.\d+)?)\s*(B|M|T|billion|million|trillion)$', re.IGNORECASE)
_PCT = re.compile(r'^([\-\+]?\d+(?:\.\d+)?)\s*%$')
_MULTIPLE = re.compile(r'^([\d]+(?:\.\d+)?)\s*[xX]$')
_PLAIN_NUM = re.compile(r'^[\-\+]?([\d,]+(?:\.\d+)?)$')
_YEAR_COL = re.compile(r'^(20\d{2}[AEae]?|FY\s*20\d{2}[AEae]?|Q[1-4]\s*20\d{2})$')


def _normalize_value(raw: str) -> tuple[float | None, str]:
    """
    Return (normalized_float, unit) for a cell value string.
    Returns (None, "text") when the value cannot be parsed numerically.
    """
    v = raw.strip()
    if not v or v in ("-", "—", "N/A", "n/a", "NA"):
        return None, "text"

    m = _DOLLAR_BIG.match(v)
    if m:
        num = float(m.group(1).replace(",", ""))
        suffix = m.group(2).upper()
        mult = {"B": 1e9, "BILLION": 1e9, "M": 1e6, "MILLION": 1e6, "T": 1e12, "TRILLION": 1e12}
        return round(num * mult.get(suffix, 1), 2), "USD"

    m = _PCT.match(v)
    if m:
        return float(m.group(1)), "percent"

    m = _MULTIPLE.match(v)
    if m:
        return float(m.group(1)), "multiple"

    m = _PLAIN_NUM.match(v)
    if m:
        return float(m.group(1).replace(",", "")), "number"

    return None, "text"


def _clean_period(col: str) -> str | None:
    """Normalize a column header to a period string, or None if not a period."""
    col = col.strip()
    if _YEAR_COL.match(col):
        return col.upper().replace("FY", "").replace(" ", "")
    return None


def _parse_table(table, table_index: int) -> dict:
    """Extract one BeautifulSoup table element into a structured dict."""
    table_id = table.get("id")

    # Extract header row
    headers = []
    thead = table.find("thead")
    if thead:
        header_cells = thead.find_all("th")
        headers = [c.get_text(strip=True) for c in header_cells]
    else:
        first_row = table.find("tr")
        if first_row:
            ths = first_row.find_all("th")
            if ths:
                headers = [c.get_text(strip=True) for c in ths]
            else:
                tds = first_row.find_all("td")
                headers = [c.get_text(strip=True) for c in tds]

    # Identify which header columns are periods
    period_map = {}  # col_index → period string
    for i, h in enumerate(headers):
        p = _clean_period(h)
        if p:
            period_map[i] = p

    period_columns = list(period_map.values())

    # Extract data rows
    rows = []
    year_value_pairs = []
    tbody = table.find("tbody")
    row_source = tbody if tbody else table
    for tr in row_source.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        # First cell is the metric label
        metric = cells[0].get_text(strip=True)
        if not metric:
            continue

        row_cells = []
        for col_idx, cell in enumerate(cells[1:], start=1):
            raw = cell.get_text(strip=True)
            period = period_map.get(col_idx)
            norm, unit = _normalize_value(raw)
            row_cells.append({
                "period": period,
                "raw_value": raw,
                "normalized_value": norm,
                "unit": unit,
            })
            if period and norm is not None:
                year_value_pairs.append({
                    "metric": metric,
                    "period": period,
                    "raw_value": raw,
                    "normalized_value": norm,
                    "unit": unit,
                })

        if row_cells:
            rows.append({"metric": metric, "cells": row_cells})

    return {
        "table_id": table_id,
        "table_index": table_index,
        "columns": headers,
        "period_columns": period_columns,
        "rows": rows,
        "year_value_pairs": year_value_pairs,
    }


def parse_report(report_path: Path) -> list[dict]:
    """Parse all tables from one HTML report. Returns list of table dicts."""
    html = report_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    results = []
    for i, table in enumerate(tables):
        parsed = _parse_table(table, i)
        # Only include tables that have at least one year column and one data row
        if parsed["period_columns"] and parsed["rows"]:
            results.append(parsed)
    return results


def run_ticker(ticker: str, report_dir: Path, output_dir: Path) -> dict:
    report_path = report_dir / f"{ticker}_Equity_Research_Report.html"
    if not report_path.exists():
        return {"ticker": ticker, "status": "report_not_found", "tables": []}

    tables = parse_report(report_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{ticker}_tables.json"
    out_path.write_text(json.dumps(tables, indent=2))

    total_pairs = sum(len(t["year_value_pairs"]) for t in tables)
    return {
        "ticker": ticker,
        "status": "ok",
        "tables_found": len(tables),
        "year_value_pairs": total_pairs,
        "output": str(out_path),
    }


ALL_TICKERS = ["COP", "MSFT", "META", "NVDA", "TSLA", "ETSY", "ROKU", "RIVN", "RBLX", "LCID"]


def main():
    parser = argparse.ArgumentParser(description="FinRobot HTML Table Parser — PR1 PoV")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", nargs="+", help="One or more ticker symbols")
    group.add_argument("--all", action="store_true", help="Run on all 10 Phase 1+2 tickers")
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    tickers = ALL_TICKERS if args.all else [t.upper() for t in args.ticker]
    summary = []
    for ticker in tickers:
        result = run_ticker(ticker, args.report_dir, args.output_dir)
        summary.append(result)
        status = result["status"]
        if status == "ok":
            print(f"  {ticker}: {result['tables_found']} tables, {result['year_value_pairs']} year-value pairs → {result['output']}")
        else:
            print(f"  {ticker}: {status}")

    print(f"\nDone. {sum(1 for r in summary if r['status']=='ok')}/{len(summary)} tickers parsed.")
    total_pairs = sum(r.get("year_value_pairs", 0) for r in summary)
    print(f"Total year-value pairs extracted: {total_pairs}")

    summary_path = args.output_dir / "_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
