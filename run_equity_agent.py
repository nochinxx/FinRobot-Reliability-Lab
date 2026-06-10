#!/usr/bin/env python
"""
run_equity_agent.py — Two-step FinRobot equity report pipeline wrapper

Usage:
    conda run -n agent python run_equity_agent.py --ticker DOCN

Steps:
    1. generate_financial_analysis.py  — fetch FMP data + generate text via LLM
    2. create_equity_report.py         — render HTML report

Output: finrobot_equity/core/output/{TICKER}/{TICKER}_Equity_Research_Report.html
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

# Company metadata for known tickers
COMPANY_META = {
    "NVDA":  {"name": "NVIDIA Corporation",        "peers": ["AMD", "INTC"]},
    "TSLA":  {"name": "Tesla, Inc.",                "peers": ["RIVN", "GM", "F"]},
    "META":  {"name": "Meta Platforms, Inc.",       "peers": ["SNAP", "PINS", "GOOGL"]},
    "MSFT":  {"name": "Microsoft Corporation",      "peers": ["GOOGL", "AAPL", "AMZN"]},
    "COP":   {"name": "ConocoPhillips",             "peers": ["XOM", "CVX", "OXY"]},
    "ETSY":  {"name": "Etsy, Inc.",                  "peers": ["AMZN", "EBAY", "PINS"]},
    "ROKU":  {"name": "Roku, Inc.",                  "peers": ["NFLX", "AMZN", "GOOGL"]},
    "RIVN":  {"name": "Rivian Automotive, Inc.",     "peers": ["TSLA", "LCID", "GM"]},
    "RBLX":  {"name": "Roblox Corporation",          "peers": ["TTWO", "EA", "ATVI"]},
    "LCID":  {"name": "Lucid Group, Inc.",           "peers": ["TSLA", "RIVN", "GM"]},
    # Phase 2 originals — NOT on FMP free tier (402), keeping for reference
    # "DOCN":  {"name": "DigitalOcean Holdings, Inc.", "peers": ["AKAM", "NET", "FSLY"]},
    # "ZI":    {"name": "ZoomInfo Technologies Inc.", "peers": ["HUBS", "DSGX", "MNDY"]},
    # "PTON":  {"name": "Peloton Interactive, Inc.",  "peers": ["NKE", "LULU", "NFLX"]},
    # "VFC":   {"name": "VF Corporation",             "peers": ["PVH", "HBI", "CROX"]},
    # "ALRM":  {"name": "Alarm.com Holdings, Inc.",   "peers": ["ARLO", "SSNC", "NRDS"]},
}

CORE_DIR = Path(__file__).parent / "finrobot_equity" / "core"
SRC_DIR = CORE_DIR / "src"
CONFIG_FILE = CORE_DIR / "config" / "config.ini"
OUTPUT_BASE = CORE_DIR / "output"


def run(cmd: list, cwd=None, log_file=None):
    print(f"\n[run_equity_agent] $ {' '.join(str(c) for c in cmd)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR) + ":" + env.get("PYTHONPATH", "")
    if log_file:
        with open(log_file, "a") as lf:
            result = subprocess.run(cmd, cwd=cwd or SRC_DIR, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            lf.write(result.stdout)
            print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    else:
        result = subprocess.run(cmd, cwd=cwd or SRC_DIR, env=env)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run FinRobot equity report pipeline")
    parser.add_argument("--ticker", required=True, type=str, help="Stock ticker (e.g. DOCN)")
    parser.add_argument("--log", type=str, default="/tmp/finrobot-phase2.log", help="Log file path")
    parser.add_argument("--peers", type=str, nargs="*", default=None, help="Peer tickers (override auto)")
    parser.add_argument("--step", type=int, choices=[1, 2], default=None, help="Run only step 1 or 2")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    meta = COMPANY_META.get(ticker, {"name": ticker, "peers": []})
    company_name = meta["name"]
    peers = args.peers or meta["peers"]

    analysis_dir = OUTPUT_BASE / ticker / "analysis"
    report_dir = OUTPUT_BASE / ticker / "report"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    log = args.log
    print(f"[run_equity_agent] Ticker: {ticker} ({company_name})")
    print(f"[run_equity_agent] Peers: {peers}")
    print(f"[run_equity_agent] Log: {log}")
    print(f"[run_equity_agent] Config: {CONFIG_FILE}")

    step1_ok = True
    if args.step in (None, 1):
        print(f"\n{'='*60}\nStep 1: Generate financial analysis\n{'='*60}")
        rc = run([
            sys.executable, "generate_financial_analysis.py",
            "--company-ticker", ticker,
            "--company-name", company_name,
            "--config-file", str(CONFIG_FILE),
            "--years-limit", "5",
            "--peer-tickers"] + peers + [
            "--generate-text-sections",
            "--output-dir", str(analysis_dir),
            "--news-days-back", "7",
            "--revenue-growth-2025", "0.05",
            "--revenue-growth-2026", "0.06",
            "--revenue-growth-2027", "0.04",
            "--margin-improvement", "0.01",
            "--sga-margin-improvement", "-0.005",
        ], log_file=log)
        if rc != 0:
            print(f"[run_equity_agent] Step 1 failed (rc={rc}) — check {log}")
            step1_ok = False

    if step1_ok and args.step in (None, 2):
        print(f"\n{'='*60}\nStep 2: Create HTML equity report\n{'='*60}")

        def opt_file(name):
            p = analysis_dir / name
            return str(p) if p.exists() else None

        cmd = [
            sys.executable, "create_equity_report.py",
            "--company-ticker", ticker,
            "--company-name", company_name,
            "--config-file", str(CONFIG_FILE),
            "--analysis-csv", str(analysis_dir / "financial_metrics_and_forecasts.csv"),
            "--ratios-csv", str(analysis_dir / "ratios_raw_data.csv"),
            "--output-dir", str(report_dir),
        ]
        for flag, fname in [
            ("--tagline-file", "tagline.txt"),
            ("--company-overview-file", "company_overview.txt"),
            ("--investment-overview-file", "investment_overview.txt"),
            ("--valuation-overview-file", "valuation_overview.txt"),
            ("--risks-file", "risks.txt"),
            ("--major-takeaways-file", "major_takeaways.txt"),
            ("--news-summary-file", "news_summary.txt"),
            ("--competitor-analysis-file", "peer_ebitda_comparison.csv"),
            ("--peer-ev-ebitda-csv", "peer_ev_ebitda_comparison.csv"),
        ]:
            v = opt_file(fname)
            if v:
                cmd += [flag, v]

        rc = run(cmd, log_file=log)
        if rc != 0:
            print(f"[run_equity_agent] Step 2 failed (rc={rc}) — check {log}")
            return

        # Rename output to the expected location for the reliability audit
        # Prefer Professional report (most text content) over Combined/Page reports
        import glob, shutil
        preferred = glob.glob(str(report_dir / "Professional_Equity_Report_*.html"))
        fallback = glob.glob(str(report_dir / "*.html"))
        reports = preferred or sorted(fallback)
        if reports:
            dest = OUTPUT_BASE / f"{ticker}_Equity_Research_Report.html"
            shutil.copy(reports[0], dest)
            print(f"\n[run_equity_agent] ✅ Report saved: {dest}")
        else:
            print(f"[run_equity_agent] ⚠️  No HTML found in {report_dir}")


if __name__ == "__main__":
    main()
