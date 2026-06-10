"""
Gate decision evaluator.

Evaluates a reliability scorecard against defined thresholds and produces a
GateDecision: PASS / HUMAN_REVIEW / FAIL.

Decision rules:
  FAIL (hard, any one triggers):
    - ICR > 0.15 (3× target)
    - SCR < 0.10 (near-zero verifiable coverage)
    - SOURCE_CONFLICT rows > 20% of total

  HUMAN_REVIEW (any one triggers, unless FAIL already):
    - Any scorecard threshold fails (ICR > 0.05, SCR < 0.80, PSCR < 0.90, UCR > 0.15)
    - valuation_dispersion > 0.10
    - Any SOURCE_CONFLICT row present

  PASS: none of the above conditions met.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_ICR_FAIL_THRESHOLD   = 0.15
_SCR_FAIL_THRESHOLD   = 0.10
_CONFLICT_FAIL_RATIO  = 0.20


def evaluate_gate(
    scorecard: dict,
    ticker: str,
    fact_rows: Optional[list[dict]] = None,
    run_id: Optional[str] = None,
    scorecard_ref: str = "",
) -> dict:
    """
    Evaluate scorecard → GateDecision dict matching gate_decision.schema.json.

    fact_rows: needed to count SOURCE_CONFLICT rows. Pass [] if unavailable.
    """
    metrics = scorecard.get("metrics", {})
    thresholds = scorecard.get("thresholds", {})
    summary = scorecard.get("summary", {})

    icr  = metrics.get("incorrect_claim_rate", 0.0) or 0.0
    scr  = metrics.get("source_coverage_rate", 0.0) or 0.0
    vd   = metrics.get("valuation_dispersion")
    total = summary.get("total_claims", 0)

    conflict_count = 0
    if fact_rows:
        conflict_count = sum(
            1 for r in fact_rows if r.get("verification_status") == "SOURCE_CONFLICT"
        )
    conflict_ratio = conflict_count / total if total > 0 else 0.0

    reasons = []
    hard_failures = []
    hr_triggers = []

    # ── Per-threshold reasons ──────────────────────────────────────────────────
    for name, info in thresholds.items():
        val   = info.get("value", 0.0)
        tgt   = info.get("target", "")
        passed = info.get("pass", True)
        reasons.append({
            "metric":    name,
            "value":     float(val),
            "threshold": tgt,
            "status":    "pass" if passed else "fail",
            "note":      None,
        })

    # ── Valuation dispersion ───────────────────────────────────────────────────
    if vd is not None:
        vd_pass = vd <= 0.10
        reasons.append({
            "metric":    "valuation_dispersion",
            "value":     float(vd),
            "threshold": "≤0.10",
            "status":    "pass" if vd_pass else "warning",
            "note":      None,
        })
        if not vd_pass:
            hr_triggers.append("high_valuation_dispersion")

    # ── SOURCE_CONFLICT ────────────────────────────────────────────────────────
    if conflict_count > 0:
        reasons.append({
            "metric":    "source_conflict_count",
            "value":     float(conflict_count),
            "threshold": "=0",
            "status":    "warning" if conflict_ratio <= _CONFLICT_FAIL_RATIO else "fail",
            "note":      f"{conflict_count} SOURCE_CONFLICT row(s)",
        })

    # ── Hard failure conditions ────────────────────────────────────────────────
    if icr > _ICR_FAIL_THRESHOLD:
        hard_failures.append(f"icr_{icr:.3f}_exceeds_fail_threshold_{_ICR_FAIL_THRESHOLD}")

    if scr < _SCR_FAIL_THRESHOLD:
        hard_failures.append(f"scr_{scr:.3f}_below_fail_threshold_{_SCR_FAIL_THRESHOLD}")

    if conflict_ratio > _CONFLICT_FAIL_RATIO:
        hard_failures.append(
            f"source_conflict_ratio_{conflict_ratio:.2f}_exceeds_{_CONFLICT_FAIL_RATIO}"
        )

    # ── HUMAN_REVIEW triggers ─────────────────────────────────────────────────
    for name, info in thresholds.items():
        if not info.get("pass", True):
            hr_triggers.append(f"{name}_below_target")

    if conflict_count > 0 and conflict_ratio <= _CONFLICT_FAIL_RATIO:
        hr_triggers.append("unresolved_source_conflict")

    # ── Decision ──────────────────────────────────────────────────────────────
    if hard_failures:
        decision = "FAIL"
    elif hr_triggers:
        decision = "HUMAN_REVIEW"
    else:
        decision = "PASS"

    return {
        "ticker":               ticker,
        "run_id":               run_id,
        "decision":             decision,
        "scorecard_ref":        scorecard_ref,
        "reasons":              reasons,
        "hard_failures":        hard_failures,
        "human_review_triggers": hr_triggers,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
    }


def save_gate_decision(gate: dict, output_dir: str, ticker: str) -> Path:
    out = Path(output_dir) / f"{ticker}_gate_decision.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gate, indent=2))
    return out
