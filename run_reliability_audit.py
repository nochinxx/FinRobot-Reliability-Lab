#!/usr/bin/env python3
"""
FinRobot Reliability Lab — main entry point.

Usage:
  python run_reliability_audit.py --ticker COP
  python run_reliability_audit.py --ticker MSFT --report path/to/report.html

Auto-discovers reports in finrobot_equity/core/output/ if --report is not given.

Outputs (in output/<TICKER>/):
  <TICKER>_claims.json
  <TICKER>_fact_table.csv
  <TICKER>_reliability_scorecard.json
  <TICKER>_audit_summary.md
"""
import argparse
import json
from pathlib import Path
from datetime import datetime

from reliability_lab.claim_extraction import extract_claims_from_report, save_claims
from reliability_lab.fact_table_builder import build_and_verify_fact_table, save_fact_table
from reliability_lab.reliability_metrics import (
    compute_scorecard, save_scorecard, format_scorecard_text
)
from reliability_lab.critic_agents import run_critic_review
from reliability_lab.recommendation_extractor import extract_recommendation
from reliability_lab.scoring.gates import evaluate_gate, save_gate_decision
from reliability_lab.backtesting.experiment_manifest import build_manifest, save_manifest
from reliability_lab.critics.quant_risk_reviewer import run_quant_risk_review
from reliability_lab.critics.model_risk_reviewer import run_model_risk_review
from reliability_lab.critics.investment_committee_memo import run_investment_committee_memo
from reliability_lab.report.annotated_report import generate_annotated_report


_REPORT_DIR = Path(__file__).parent / "finrobot_equity" / "core" / "output"


def _find_report(ticker: str) -> Path:
    """Auto-discover report in finrobot_equity/core/output/."""
    candidates = [
        _REPORT_DIR / f"{ticker}_Equity_Research_Report.html",
        _REPORT_DIR / f"{ticker.upper()}_Equity_Research_Report.html",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"No report found for {ticker} in {_REPORT_DIR}. "
        f"Pass --report to specify the path explicitly."
    )


def write_audit_summary(
    ticker: str,
    scorecard: dict,
    fact_rows: list[dict],
    output_dir: str,
    report_path: str,
) -> Path:
    out = Path(output_dir) / f"{ticker}_audit_summary.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    s = scorecard.get("summary", {})
    m = scorecard.get("metrics", {})
    t = scorecard.get("thresholds", {})

    lines = [
        f"# FinRobot Reliability Audit — {ticker}",
        f"*Generated: {ts}*",
        f"*Report: `{report_path}`*",
        "",
        "## Scorecard",
        "",
        f"| Metric | Value | Target | Status |",
        f"|--------|-------|--------|--------|",
    ]
    for metric, info in t.items():
        status = "✅ PASS" if info["pass"] else "❌ FAIL"
        lines.append(f"| {metric.replace('_', ' ')} | {info['value']:.3f} | {info['target']} | {status} |")

    if m.get("valuation_dispersion") is not None:
        lines.append(f"| valuation dispersion | {m['valuation_dispersion']:.3f} | ≤0.10 | {'✅' if m['valuation_dispersion'] <= 0.10 else '❌'} |")

    lines += [
        "",
        "## Claim Counts",
        "",
        f"- **Total claims extracted:** {s.get('total_claims', 0)}",
        f"- **Machine-verifiable:** {s.get('machine_verifiable_claims', 0)}",
        f"  - Verified correct: {s.get('verified_count', 0)}",
        f"  - Verified incorrect: {s.get('incorrect_count', 0)}",
        f"- **Unsupported:** {s.get('unsupported_count', 0)}",
        f"- **Not machine-verifiable (guidance/forward):** {s.get('not_machine_verifiable', 0)}",
        "",
        "## Verified Claims",
        "",
    ]

    verified = [r for r in fact_rows if r["verification_status"] == "verified"]
    if verified:
        lines.append("| Metric | Period | Claimed | Verified | Source |")
        lines.append("|--------|--------|---------|----------|--------|")
        for r in verified:
            lines.append(
                f"| {r['metric']} | {r['period']} | {r['claimed_value']} "
                f"| {r['verified_value']} | {r['source']} |"
            )
    else:
        lines.append("*No claims verified against primary sources.*")

    lines += ["", "## Incorrect Claims", ""]

    incorrect = [r for r in fact_rows if r["verification_status"] == "incorrect"]
    if incorrect:
        lines.append("| Metric | Period | Claimed | Actual | Source |")
        lines.append("|--------|--------|---------|--------|--------|")
        for r in incorrect:
            lines.append(
                f"| {r['metric']} | {r['period']} | {r['claimed_value']} "
                f"| {r['verified_value']} | {r['source']} |"
            )
    else:
        lines.append("*No incorrect claims found in machine-verifiable set.*")

    lines += [
        "",
        "## Per-Metric Breakdown",
        "",
        "| Metric | Total | Verified | Incorrect | Unsupported | NMV |",
        "|--------|-------|----------|-----------|-------------|-----|",
    ]
    for metric, counts in scorecard.get("by_metric", {}).items():
        lines.append(
            f"| {metric} | {counts['total']} | {counts['verified']} "
            f"| {counts['incorrect']} | {counts['unsupported']} "
            f"| {counts['not_machine_verifiable']} |"
        )

    lines += [
        "",
        "## Methodology Notes",
        "",
        "- Extraction method: regex (LLM extraction available when ANTHROPIC_API_KEY is set)",
        "- Revenue/EBITDA verified via SEC EDGAR XBRL facts API (no API key required)",
        "- Tolerance: 2% for revenue figures (accounts for rounding in report)",
        "- Guidance and forward-looking claims marked `not_machine_verifiable`",
        "- Peer comparison figures not cross-checked in this run",
    ]

    out.write_text("\n".join(lines))
    return out


def main():
    parser = argparse.ArgumentParser(description="FinRobot Reliability Audit")
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. COP)")
    parser.add_argument("--report", default=None,
                        help="Path to FinRobot HTML report (auto-discovered if omitted)")
    parser.add_argument("--mode", default="auto",
                        choices=["auto", "regex", "llm"],
                        help="Claim extraction mode")
    parser.add_argument("--output-dir", default=None,
                        help="Output directory (default: output/<TICKER>/)")
    parser.add_argument("--critic", action="store_true",
                        help="Run Phase 5 adversarial critic review (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--recommendation", action="store_true",
                        help="Extract structured recommendation JSON (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--gate", action="store_true",
                        help="Emit gate decision JSON after scorecard (Phase 3b)")
    parser.add_argument("--manifest", action="store_true",
                        help="Emit experiment manifest JSON capturing run reproducibility")
    parser.add_argument("--memo", action="store_true",
                        help="Generate investment committee memo (Phase 7; requires ANTHROPIC_API_KEY)")
    parser.add_argument("--annotate", action="store_true",
                        help="Generate annotated HTML audit report (Phase 4b)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    output_dir = args.output_dir or f"output/{ticker}"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Find report
    report_path = args.report
    if not report_path:
        try:
            report_path = str(_find_report(ticker))
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            return 1

    print(f"\n{'━'*50}")
    print(f"  FinRobot Reliability Audit: {ticker}")
    print(f"  Report: {report_path}")
    print(f"  Mode:   {args.mode}")
    print(f"{'━'*50}\n")

    print("Phase 1: Extracting claims...")
    claims = extract_claims_from_report(report_path, ticker, mode=args.mode)
    claims_path = save_claims(claims, output_dir, ticker)
    print(f"  → {len(claims)} claims extracted → {claims_path}")
    if not claims:
        print("  WARNING: No claims extracted. Report may need manual review.")

    print("\nPhase 2: Verifying claims against primary sources...")
    rows = build_and_verify_fact_table(claims, ticker)
    fact_path = save_fact_table(rows, output_dir, ticker)
    verified = sum(1 for r in rows if r["verification_status"] == "verified")
    incorrect = sum(1 for r in rows if r["verification_status"] == "incorrect")
    print(f"  → {len(rows)} rows, {verified} verified, {incorrect} incorrect → {fact_path}")

    print("\nPhase 3: Computing reliability scorecard...")
    scorecard = compute_scorecard(rows, claims)
    score_path = save_scorecard(scorecard, output_dir, ticker)
    print(f"  → {score_path}")

    print("\nPhase 4: Writing audit summary...")
    summary_path = write_audit_summary(ticker, scorecard, rows, output_dir, report_path)
    print(f"  → {summary_path}")

    print(f"\n{'━'*50}")
    print(format_scorecard_text(scorecard, ticker))
    print(f"{'━'*50}")
    print(f"\nAll outputs in: {output_dir}/")

    # Phase 4b: Annotated HTML report
    if args.annotate:
        print(f"\nPhase 4b: Generating annotated HTML report...")
        annotated_path = generate_annotated_report(
            ticker=ticker,
            scorecard=scorecard,
            fact_rows=rows,
            output_dir=output_dir,
            report_path=report_path,
        )
        print(f"  → {annotated_path}")

    # Phase 3b: Gate decision
    if args.gate:
        print(f"\nPhase 3b: Evaluating gate decision...")
        scorecard_ref = str(score_path)
        gate = evaluate_gate(
            scorecard=scorecard,
            ticker=ticker,
            fact_rows=rows,
            scorecard_ref=scorecard_ref,
        )
        gate_path = save_gate_decision(gate, output_dir, ticker)
        print(f"  → Decision: {gate['decision']}  ({gate_path})")
        if gate["hard_failures"]:
            print(f"  Hard failures: {gate['hard_failures']}")
        if gate["human_review_triggers"]:
            print(f"  Human-review triggers: {gate['human_review_triggers']}")

    # Phase 3c: Experiment manifest
    if args.manifest:
        print(f"\nPhase 3c: Writing experiment manifest...")
        phases = ["claim_extraction", "fact_verification"]
        if args.critic:
            phases.append("adversarial_critic")
        outputs = [str(claims_path), str(fact_path), str(score_path), str(summary_path)]
        manifest = build_manifest(
            ticker=ticker,
            mode=args.mode,
            phases=phases,
            description=f"Reliability audit: {ticker}",
            data_sources=[
                {"source_name": "SEC EDGAR XBRL", "tier": 1, "cache_hit": None},
                {"source_name": "FMP free tier",  "tier": 3, "cache_hit": None},
            ],
            outputs=outputs,
        )
        manifest_path = save_manifest(manifest, output_dir, ticker)
        print(f"  → {manifest_path}")

    # Phase 6: Recommendation extraction (runs by default; --recommendation is now a no-op)
    print(f"\n{'━'*50}")
    print("  Phase 6: Recommendation Extraction")
    print(f"{'━'*50}")
    rec = extract_recommendation(
        report_path=report_path,
        ticker=ticker,
        output_dir=output_dir,
    )
    if rec and not rec.get("parse_error"):
        rating = rec.get("rating", {})
        pt = rec.get("price_target", {})
        print(f"  Rating:       {rating.get('value', 'N/A')}")
        print(f"  Price target: {pt.get('value', 'N/A')}")
        print(f"  → output/{ticker}/{ticker}_recommendation.json")
    else:
        print("  Recommendation extraction skipped (no API key or parse error)")

    if args.critic:
        print(f"\n{'━'*50}")
        print("  Phase 5a: Adversarial Critic Review")
        print(f"{'━'*50}")
        critic_result = run_critic_review(
            ticker=ticker,
            report_path=report_path,
            fact_rows=rows,
            scorecard=scorecard,
            output_dir=output_dir,
        )
        if critic_result:
            print(f"\n  Original rec:  {critic_result['original_recommendation']}")
            print(f"  Revised rec:   {critic_result['revised_recommendation']}")
            print(f"  Thesis stability score: {critic_result['thesis_stability_score']:.3f}")
        else:
            print("  Adversarial critic skipped (no API key or report missing)")

        print(f"\n{'━'*50}")
        print("  Phase 5b: Quant Risk Review")
        print(f"{'━'*50}")
        qr = run_quant_risk_review(
            ticker=ticker,
            scorecard=scorecard,
            fact_rows=rows,
            output_dir=output_dir,
        )
        if qr and not qr.get("parse_error"):
            print(f"  Quant risk verdict: {qr.get('quant_risk_verdict', 'N/A')}")
            print(f"  Rationale: {qr.get('quant_risk_rationale', '')[:120]}")
        else:
            print("  Quant risk review skipped (no API key or parse error)")

        print(f"\n{'━'*50}")
        print("  Phase 5c: Model Risk Review")
        print(f"{'━'*50}")
        mr = run_model_risk_review(
            ticker=ticker,
            scorecard=scorecard,
            output_dir=output_dir,
        )
        if mr and not mr.get("parse_error"):
            print(f"  Model risk verdict: {mr.get('model_risk_verdict', 'N/A')}")
            conds = mr.get("conditions_for_upgrade", [])
            if conds:
                print(f"  Upgrade conditions ({len(conds)}): {conds[0][:80]}...")
        else:
            print("  Model risk review skipped (no API key or parse error)")

    if args.memo:
        print(f"\n{'━'*50}")
        print("  Phase 7: Investment Committee Memo")
        print(f"{'━'*50}")
        gate_for_memo = None
        if args.gate:
            gate_for_memo = evaluate_gate(
                scorecard=scorecard, ticker=ticker, fact_rows=rows,
                scorecard_ref=str(score_path),
            )
        run_investment_committee_memo(
            ticker=ticker,
            scorecard=scorecard,
            fact_rows=rows,
            output_dir=output_dir,
            gate=gate_for_memo,
        )

    return 0


if __name__ == "__main__":
    exit(main())
