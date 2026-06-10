#!/usr/bin/env python3
"""
Batch reliability audit — run all benchmark tickers and produce a comparison table.

Usage:
    conda run -n agent python run_batch_audit.py
    conda run -n agent python run_batch_audit.py --phase1
    conda run -n agent python run_batch_audit.py --phase2
    conda run -n agent python run_batch_audit.py --tickers NVDA TSLA --mode regex

Outputs:
    output/batch_results.md   — comparison table across tickers
    output/master_fact_table.csv  — merged fact table (via run_master_fact_table)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

PHASE1 = ["NVDA", "TSLA", "META", "MSFT", "COP"]
PHASE2 = ["ETSY", "ROKU", "RIVN", "RBLX", "LCID"]
ALL    = PHASE1 + PHASE2


def run_ticker(ticker: str, mode: str, extra_flags: list[str]) -> dict:
    cmd = [
        "conda", "run", "-n", "agent", "python",
        "run_reliability_audit.py",
        "--ticker", ticker,
        "--mode", mode,
        *extra_flags,
    ]
    print(f"\n{'─'*50}")
    print(f"  Auditing: {ticker}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr[-200:]}")
        return {"ticker": ticker, "error": True}

    # Load scorecard
    sc_path = Path(f"output/{ticker}/{ticker}_reliability_scorecard.json")
    if not sc_path.exists():
        return {"ticker": ticker, "error": True}

    sc = json.loads(sc_path.read_text())
    m = sc.get("metrics", {})
    s = sc.get("summary", {})

    gate_path = Path(f"output/{ticker}/{ticker}_gate_decision.json")
    gate = None
    if gate_path.exists():
        gate = json.loads(gate_path.read_text()).get("decision", "N/A")

    return {
        "ticker": ticker,
        "total_claims": s.get("total_claims", 0),
        "mv_claims": s.get("machine_verifiable_claims", 0),
        "verified": s.get("verified_count", 0),
        "incorrect": s.get("incorrect_count", 0),
        "scr": m.get("source_coverage_rate", 0.0),
        "icr": m.get("incorrect_claim_rate", 0.0),
        "vd": m.get("valuation_dispersion"),
        "gate": gate or "N/A",
    }


def build_comparison_table(results: list[dict]) -> str:
    lines = [
        "# Batch Reliability Audit — Comparison Table\n",
        "| Ticker | Claims | MV | ✅ | ❌ | SCR | ICR | VD | Gate |",
        "|--------|--------|----|----|-----|-----|-----|-----|------|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['ticker']} | ERROR | | | | | | | |")
            continue
        vd = f"{r['vd']:.3f}" if r["vd"] is not None else "N/A"
        lines.append(
            f"| {r['ticker']} "
            f"| {r['total_claims']} "
            f"| {r['mv_claims']} "
            f"| {r['verified']} "
            f"| {r['incorrect']} "
            f"| {r['scr']:.3f} "
            f"| {r['icr']:.3f} "
            f"| {vd} "
            f"| {r['gate']} |"
        )

    # Aggregate row
    valid = [r for r in results if not r.get("error")]
    if valid:
        total_mv = sum(r["mv_claims"] for r in valid)
        total_claims = sum(r["total_claims"] for r in valid)
        total_ver = sum(r["verified"] for r in valid)
        total_inc = sum(r["incorrect"] for r in valid)
        agg_scr = total_mv / total_claims if total_claims else 0
        agg_icr = total_inc / total_mv if total_mv else 0
        lines.append(
            f"| **ALL** "
            f"| **{total_claims}** "
            f"| **{total_mv}** "
            f"| **{total_ver}** "
            f"| **{total_inc}** "
            f"| **{agg_scr:.3f}** "
            f"| **{agg_icr:.3f}** "
            f"| — "
            f"| — |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Batch reliability audit")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--phase1",  action="store_true", help="Phase 1 tickers only (GPT-4 reports)")
    group.add_argument("--phase2",  action="store_true", help="Phase 2 tickers only (Gemma4 reports)")
    group.add_argument("--tickers", nargs="+", metavar="TICKER")
    parser.add_argument("--mode",   default="regex", choices=["auto", "regex", "llm"])
    parser.add_argument("--gate",   action="store_true", help="Include gate decision (--gate flag)")
    args = parser.parse_args()

    if args.phase1:
        tickers = PHASE1
    elif args.phase2:
        tickers = PHASE2
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = ALL

    extra = ["--gate"] if args.gate else []

    print(f"Batch audit: {len(tickers)} tickers, mode={args.mode}")
    results = [run_ticker(t, args.mode, extra) for t in tickers]

    table = build_comparison_table(results)
    print(f"\n{'═'*60}")
    print(table)

    out = Path("output/batch_results.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(table)
    print(f"\nSaved → {out}")

    # Also run master fact table merge
    subprocess.run([
        "conda", "run", "-n", "agent", "python",
        "run_master_fact_table.py",
    ], capture_output=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
