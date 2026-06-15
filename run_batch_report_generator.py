#!/usr/bin/env python
"""
Batch FinRobot report generator — G1 prerequisite.

Generates HTML equity research reports for new tickers using Gemma4 via Ollama.
Reports are saved to finrobot_equity/core/output/{TICKER}_Equity_Research_Report.html.

Usage:
    # Generate all Batch A tickers (30 tickers)
    conda run -n agent python run_batch_report_generator.py --batch A

    # Generate specific tickers
    conda run -n agent python run_batch_report_generator.py --tickers AAPL GOOGL AMZN

    # Dry-run (print commands without executing)
    conda run -n agent python run_batch_report_generator.py --batch A --dry-run

    # Resume (skip tickers that already have reports)
    conda run -n agent python run_batch_report_generator.py --batch A --skip-existing
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).parent
_FIN_SRC = _ROOT / "finrobot_equity" / "core" / "src"
_OUTPUT = _ROOT / "finrobot_equity" / "core" / "output"

# ── Ticker universe ────────────────────────────────────────────────────────────

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com Inc.",
    "NFLX": "Netflix Inc.",
    "AMD": "Advanced Micro Devices Inc.",
    "INTC": "Intel Corporation",
    "ORCL": "Oracle Corporation",
    "CRM": "Salesforce Inc.",
    "ADBE": "Adobe Inc.",
    "QCOM": "Qualcomm Incorporated",
    "TXN": "Texas Instruments Incorporated",
    "AMAT": "Applied Materials Inc.",
    "MU": "Micron Technology Inc.",
    "AVGO": "Broadcom Inc.",
    "NOW": "ServiceNow Inc.",
    "PANW": "Palo Alto Networks Inc.",
    "CRWD": "CrowdStrike Holdings Inc.",
    "JNJ": "Johnson & Johnson",
    "PFE": "Pfizer Inc.",
    "UNH": "UnitedHealth Group Inc.",
    "ABBV": "AbbVie Inc.",
    "MRK": "Merck & Co. Inc.",
    "BMY": "Bristol-Myers Squibb Company",
    "GILD": "Gilead Sciences Inc.",
    "AMGN": "Amgen Inc.",
    "TMO": "Thermo Fisher Scientific Inc.",
    "DHR": "Danaher Corporation",
    "ABT": "Abbott Laboratories",
    "MDT": "Medtronic plc",
    "LLY": "Eli Lilly and Company",
    "JPM": "JPMorgan Chase & Co.",
    "BAC": "Bank of America Corporation",
    "GS": "The Goldman Sachs Group Inc.",
    "MS": "Morgan Stanley",
    "BLK": "BlackRock Inc.",
    "V": "Visa Inc.",
    "MA": "Mastercard Incorporated",
    "AXP": "American Express Company",
    "C": "Citigroup Inc.",
    "WFC": "Wells Fargo & Company",
    "SCHW": "The Charles Schwab Corporation",
    "ICE": "Intercontinental Exchange Inc.",
    "WMT": "Walmart Inc.",
    "COST": "Costco Wholesale Corporation",
    "TGT": "Target Corporation",
    "HD": "The Home Depot Inc.",
    "NKE": "Nike Inc.",
    "SBUX": "Starbucks Corporation",
    "MCD": "McDonald's Corporation",
    "DIS": "The Walt Disney Company",
    "CMCSA": "Comcast Corporation",
    "PEP": "PepsiCo Inc.",
    "KO": "The Coca-Cola Company",
    "PG": "Procter & Gamble Company",
    "ISRG": "Intuitive Surgical Inc.",
    "SNPS": "Synopsys Inc.",
    "ZS": "Zscaler Inc.",
    "NET": "Cloudflare Inc.",
    "DDOG": "Datadog Inc.",
    "SNOW": "Snowflake Inc.",
    "MDB": "MongoDB Inc.",
    "TEAM": "Atlassian Corporation",
    "CAT": "Caterpillar Inc.",
    "DE": "Deere & Company",
    "GE": "GE Aerospace",
    "HON": "Honeywell International Inc.",
    "RTX": "RTX Corporation",
    "LMT": "Lockheed Martin Corporation",
    "UPS": "United Parcel Service Inc.",
    "BA": "The Boeing Company",
    "ETN": "Eaton Corporation plc",
    "T": "AT&T Inc.",
    "VZ": "Verizon Communications Inc.",
    "TMUS": "T-Mobile US Inc.",
    "CHTR": "Charter Communications Inc.",
    "WBD": "Warner Bros. Discovery Inc.",
    "LIN": "Linde plc",
    "APD": "Air Products and Chemicals Inc.",
    "ECL": "Ecolab Inc.",
    "NUE": "Nucor Corporation",
    "FCX": "Freeport-McMoRan Inc.",
    "AMT": "American Tower Corporation",
    "PLD": "Prologis Inc.",
    "EQIX": "Equinix Inc.",
    "SPG": "Simon Property Group Inc.",
    "PSA": "Public Storage",
    "NEE": "NextEra Energy Inc.",
    "DUK": "Duke Energy Corporation",
    "SO": "The Southern Company",
    "AEP": "American Electric Power Company Inc.",
}

BATCH_A = [
    "AAPL", "GOOGL", "AMZN", "NFLX", "AMD", "INTC", "ORCL", "CRM", "ADBE", "QCOM",
    "TXN", "AMAT", "MU", "AVGO", "NOW", "PANW", "CRWD", "JNJ", "PFE", "UNH",
    "ABBV", "MRK", "BMY", "GILD", "AMGN", "TMO", "DHR", "ABT", "MDT", "LLY",
]

BATCH_B = [
    "JPM", "BAC", "GS", "MS", "BLK", "V", "MA", "AXP", "C", "WFC",
    "SCHW", "ICE", "WMT", "COST", "TGT", "HD", "NKE", "SBUX", "MCD", "DIS",
    "CMCSA", "PEP", "KO", "PG", "ISRG", "SNPS", "ZS", "NET", "DDOG", "SNOW",
]

BATCH_C = [
    "MDB", "TEAM", "CAT", "DE", "GE", "HON", "RTX", "LMT", "UPS", "BA",
    "ETN", "T", "VZ", "TMUS", "CHTR", "WBD", "LIN", "APD", "ECL", "NUE",
    "FCX", "AMT", "PLD", "EQIX", "SPG", "PSA", "NEE", "DUK", "SO", "AEP",
]

ALREADY_DONE = [
    "COP", "MSFT", "META", "NVDA", "TSLA",
    "ETSY", "ROKU", "RIVN", "RBLX", "LCID",
]

BATCHES = {"A": BATCH_A, "B": BATCH_B, "C": BATCH_C}


def report_exists(ticker: str) -> bool:
    path = _OUTPUT / f"{ticker}_Equity_Research_Report.html"
    return path.exists()


def analysis_complete(ticker: str) -> bool:
    """True if all expected analysis files exist for ticker."""
    analysis_dir = _OUTPUT / ticker / "analysis"
    required = [
        "financial_metrics_and_forecasts.csv", "ratios_raw_data.csv",
        "tagline.txt", "company_overview.txt", "investment_overview.txt",
        "valuation_overview.txt", "risks.txt", "competitor_analysis.txt",
        "major_takeaways.txt", "news_summary.txt",
    ]
    return all((analysis_dir / f).exists() for f in required)


def generate_report(ticker: str, dry_run: bool = False, html_only: bool = False) -> bool:
    """
    Run the FinRobot financial analysis + report generation pipeline for one ticker.
    --html-only: skip generate_financial_analysis.py; use pre-existing analysis files.
    Returns True on success.
    """
    company_name = COMPANY_NAMES.get(ticker, f"{ticker} Corporation")
    analysis_dir = _OUTPUT / ticker / "analysis"

    # Step 1: generate financial analysis data + text sections (skipped in html_only mode)
    analysis_cmd = [
        "conda", "run", "-n", "agent", "python",
        str(_FIN_SRC / "generate_financial_analysis.py"),
        "--company-ticker", ticker,
        "--company-name", company_name,
        "--generate-text-sections",
        "--output-dir", str(analysis_dir),
    ]

    report_dir = _OUTPUT / ticker / "report"

    def _file(name: str) -> str:
        return str(analysis_dir / name)

    # Step 2: assemble HTML report from analysis files
    report_cmd = [
        "conda", "run", "-n", "agent", "python",
        str(_FIN_SRC / "create_equity_report.py"),
        "--company-ticker", ticker,
        "--company-name", company_name,
        "--analysis-csv", _file("financial_metrics_and_forecasts.csv"),
        "--ratios-csv", _file("ratios_raw_data.csv"),
        "--tagline-file", _file("tagline.txt"),
        "--company-overview-file", _file("company_overview.txt"),
        "--investment-overview-file", _file("investment_overview.txt"),
        "--valuation-overview-file", _file("valuation_overview.txt"),
        "--risks-file", _file("risks.txt"),
        "--competitor-analysis-file", _file("competitor_analysis.txt"),
        "--major-takeaways-file", _file("major_takeaways.txt"),
        "--news-summary-file", _file("news_summary.txt"),
        "--output-dir", str(report_dir),
        "--skip-auto-fetch",  # never consume FMP quota during HTML assembly
    ]

    if dry_run:
        mode = "html-only" if html_only else "full"
        print(f"[DRY-RUN] {ticker} ({mode}): analysis → {str(analysis_dir)}")
        print(f"[DRY-RUN] {ticker} ({mode}): report → {str(report_dir)}")
        return True

    print(f"\n{'='*60}")
    mode_label = "HTML assembly (existing analysis)" if html_only else "Full pipeline"
    print(f"{mode_label}: {ticker} ({company_name})")
    print(f"{'='*60}")

    t0 = time.time()
    try:
        analysis_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)

        if not html_only:
            result = subprocess.run(
                analysis_cmd,
                cwd=str(_FIN_SRC),
                capture_output=False,
                timeout=10800,  # 3h — Ollama text generation can take 90-120 min per ticker
            )
            if result.returncode != 0:
                print(f"[ERROR] {ticker}: financial analysis failed (exit {result.returncode})")
                return False
        else:
            if not analysis_complete(ticker):
                print(f"[ERROR] {ticker}: --html-only requested but analysis files incomplete")
                return False
            print(f"[OK] {ticker}: using existing analysis files")

        result2 = subprocess.run(
            report_cmd,
            cwd=str(_FIN_SRC),
            capture_output=False,
            timeout=300,  # HTML assembly is fast
        )
        if result2.returncode != 0:
            print(f"[WARN] {ticker}: HTML report assembly returned non-zero")

        # Copy Professional report to top-level (where audit expects it)
        import shutil
        pro_report = report_dir / f"Professional_Equity_Report_{ticker}.html"
        if pro_report.exists():
            dest = _OUTPUT / f"{ticker}_Equity_Research_Report.html"
            shutil.copy2(pro_report, dest)
            print(f"[OK] {ticker}: report copied to {dest.name}")

        elapsed = time.time() - t0
        if report_exists(ticker):
            print(f"[OK] {ticker}: report ready in {elapsed:.0f}s")
            return True
        else:
            print(f"[WARN] {ticker}: finished in {elapsed:.0f}s but {ticker}_Equity_Research_Report.html not found")
            return False

    except subprocess.TimeoutExpired:
        print(f"[ERROR] {ticker}: timed out (analysis step allows 3h)")
        return False
    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch FinRobot report generator")
    parser.add_argument("--batch", choices=["A", "B", "C"], help="Run a predefined batch")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to generate")
    parser.add_argument("--dry-run", action="store_true", help="Print commands, don't execute")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip tickers that already have reports (default: on)")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if report exists")
    parser.add_argument("--html-only", action="store_true",
                        help="Skip generate_financial_analysis.py; assemble HTML from pre-existing analysis files only (no FMP calls)")
    args = parser.parse_args()

    if not args.batch and not args.tickers:
        parser.print_help()
        sys.exit(1)

    tickers = args.tickers or BATCHES[args.batch]
    skip = args.skip_existing and not args.force

    results = {"ok": [], "skipped": [], "failed": []}

    for ticker in tickers:
        if ticker in ALREADY_DONE:
            print(f"[SKIP] {ticker}: already in benchmark")
            results["skipped"].append(ticker)
            continue
        if skip and report_exists(ticker):
            print(f"[SKIP] {ticker}: report exists")
            results["skipped"].append(ticker)
            continue
        if ticker not in COMPANY_NAMES:
            print(f"[WARN] {ticker}: not in COMPANY_NAMES dict — skipping")
            results["failed"].append(ticker)
            continue

        ok = generate_report(ticker, dry_run=args.dry_run, html_only=args.html_only)
        if ok:
            results["ok"].append(ticker)
        else:
            results["failed"].append(ticker)

    print(f"\n{'='*60}")
    print(f"DONE: {len(results['ok'])} generated, {len(results['skipped'])} skipped, {len(results['failed'])} failed")
    if results["failed"]:
        print(f"Failed: {', '.join(results['failed'])}")
    if results["ok"]:
        print(f"Generated: {', '.join(results['ok'])}")
    print(f"{'='*60}")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
