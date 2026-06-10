"""
Compute reliability scorecard from a verified fact table.

Metrics:
  total_claims                  — total claims extracted
  machine_verifiable_claims     — claims that can be checked against primary sources
  verified_count                — confirmed correct against primary source
  incorrect_count               — confirmed wrong against primary source
  unsupported_count             — no primary source available
  source_coverage_rate          — (verified + incorrect) / total  [machine-checkable ratio]
  primary_source_coverage_rate  — verified / machine_verifiable
  unsupported_claim_rate        — unsupported / total
  incorrect_claim_rate          — incorrect / machine_verifiable
  valuation_dispersion          — stdev/mean of valuation multiples (if ≥2 available)
  by_metric                     — per-metric breakdown
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path


_TARGET_SCR    = 0.80   # source coverage rate
_TARGET_PSCR   = 0.90   # primary source coverage rate
_TARGET_UCR    = 0.15   # unsupported claim rate max
_TARGET_ICR    = 0.05   # incorrect claim rate max
_TARGET_VD     = 0.10   # valuation dispersion max


def compute_scorecard(fact_rows: list[dict], claims: list[dict] = None) -> dict:
    total = len(fact_rows)
    if total == 0:
        return {"error": "no claims to score"}

    # Status counts
    status_counts = defaultdict(int)
    for r in fact_rows:
        status_counts[r.get("verification_status", "unsupported")] += 1

    verified   = status_counts["verified"]
    incorrect  = status_counts["incorrect"]
    unsupported = status_counts["unsupported"]
    nmv        = status_counts["not_machine_verifiable"]
    machine_verifiable = verified + incorrect

    # Valuation dispersion (multiples)
    multiples = []
    for r in fact_rows:
        if r.get("metric") in ("pe_ratio", "ev_ebitda") and r.get("claimed_value"):
            try:
                v_str = str(r["claimed_value"]).replace("x", "").strip()
                multiples.append(float(v_str))
            except (ValueError, TypeError):
                pass

    vd = None
    if len(multiples) >= 2:
        try:
            vd = round(statistics.stdev(multiples) / statistics.mean(multiples), 3)
        except statistics.StatisticsError:
            vd = None

    # Per-metric breakdown
    by_metric = defaultdict(lambda: {"total": 0, "verified": 0, "incorrect": 0,
                                      "unsupported": 0, "not_machine_verifiable": 0})
    for r in fact_rows:
        metric = r.get("metric", "unknown")
        by_metric[metric]["total"] += 1
        by_metric[metric][r.get("verification_status", "unsupported")] += 1

    # Compute derived rates
    scr  = round(machine_verifiable / total, 3) if total > 0 else 0.0
    pscr = round(verified / machine_verifiable, 3) if machine_verifiable > 0 else 0.0
    ucr  = round(unsupported / total, 3) if total > 0 else 0.0
    icr  = round(incorrect / machine_verifiable, 3) if machine_verifiable > 0 else 0.0

    # Pass/fail thresholds
    thresholds = {
        "source_coverage_rate":         {"value": scr,  "target": f"≥{_TARGET_SCR}", "pass": scr >= _TARGET_SCR},
        "primary_source_coverage_rate": {"value": pscr, "target": f"≥{_TARGET_PSCR}", "pass": pscr >= _TARGET_PSCR},
        "unsupported_claim_rate":       {"value": ucr,  "target": f"≤{_TARGET_UCR}", "pass": ucr <= _TARGET_UCR},
        "incorrect_claim_rate":         {"value": icr,  "target": f"≤{_TARGET_ICR}", "pass": icr <= _TARGET_ICR},
    }

    scorecard = {
        "summary": {
            "total_claims":               total,
            "machine_verifiable_claims":  machine_verifiable,
            "verified_count":             verified,
            "incorrect_count":            incorrect,
            "unsupported_count":          unsupported,
            "not_machine_verifiable":     nmv,
        },
        "metrics": {
            "source_coverage_rate":         scr,
            "primary_source_coverage_rate": pscr,
            "unsupported_claim_rate":       ucr,
            "incorrect_claim_rate":         icr,
            "valuation_dispersion":         vd,
        },
        "thresholds": thresholds,
        "by_metric":  dict(by_metric),
    }
    return scorecard


def format_scorecard_text(scorecard: dict, ticker: str) -> str:
    """Human-readable scorecard summary."""
    s = scorecard.get("summary", {})
    m = scorecard.get("metrics", {})
    t = scorecard.get("thresholds", {})

    lines = [
        f"━━━ {ticker} Reliability Scorecard ━━━",
        f"Claims extracted: {s.get('total_claims', 0)}",
        f"  Machine-verifiable: {s.get('machine_verifiable_claims', 0)}",
        f"  Verified correct:   {s.get('verified_count', 0)}",
        f"  Verified incorrect: {s.get('incorrect_count', 0)}",
        f"  Unsupported:        {s.get('unsupported_count', 0)}",
        f"  Not machine-verifiable: {s.get('not_machine_verifiable', 0)}",
        "",
        "Reliability Metrics:",
    ]

    for metric, info in t.items():
        status = "PASS" if info["pass"] else "FAIL"
        lines.append(f"  [{status}] {metric}: {info['value']:.3f}  (target {info['target']})")

    if m.get("valuation_dispersion") is not None:
        lines.append(f"  [INFO] valuation_dispersion: {m['valuation_dispersion']:.3f}")

    return "\n".join(lines)


def save_scorecard(scorecard: dict, output_dir: str, ticker: str) -> Path:
    out = Path(output_dir) / f"{ticker}_reliability_scorecard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scorecard, indent=2))
    return out
