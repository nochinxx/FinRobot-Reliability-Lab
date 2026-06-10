"""
Audit-level statistics: ICR decomposition, coverage analysis,
cross-ticker comparison, and ICR→alpha hypothesis testing.

These functions operate on the output CSVs and backtest snapshots
produced by run_reliability_audit.py and run_historical_backtest.py.
"""
import csv
import json
from pathlib import Path
from typing import Optional

try:
    from scipy.stats import spearmanr, kendalltau
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── ICR decomposition ─────────────────────────────────────────────────────────

# Report cutoff: claims for FY >= FORWARD_YEAR_CUTOFF are forward projections
# (FinRobot reports generated ~March 2026 using data through FY2024)
FORWARD_YEAR_CUTOFF = 2025

# Growth metrics prone to YoY computation artifacts when period < 2023
GROWTH_ARTIFACT_METRICS = {"revenue_growth", "ebitda_margin", "growth_rate"}
GROWTH_ARTIFACT_PERIODS = {"2020", "2021", "2022"}


def classify_incorrect_claim(row: dict) -> str:
    """
    Classify one incorrect fact table row into an error category.

    Categories:
      forward_projection   — period >= 2025; claim is a projection now verifiable
      growth_misattribution — revenue_growth / ebitda_margin in 2020-22 period;
                              driven by YoY computation mismatch, not data error
      genuine_error         — all other incorrect claims
    """
    period  = str(row.get("period", "") or "").strip()
    metric  = str(row.get("metric", "") or "").strip()

    try:
        year = int(period[:4]) if period else 0
    except ValueError:
        year = 0

    if year >= FORWARD_YEAR_CUTOFF:
        return "forward_projection"

    if metric in GROWTH_ARTIFACT_METRICS and period in GROWTH_ARTIFACT_PERIODS:
        return "growth_misattribution"

    return "genuine_error"


def decompose_icr(fact_rows: list[dict]) -> dict:
    """
    Decompose incorrect claims by category across a fact table.

    Returns:
      total_incorrect, forward_projection (n + %), growth_misattribution (n + %),
      genuine_error (n + %), machine_verifiable, icr, adjusted_icr
    """
    incorrect = [r for r in fact_rows if r.get("verification_status") == "incorrect"]
    mv = sum(1 for r in fact_rows if r.get("verification_status") in ("verified", "incorrect"))

    if not incorrect:
        return {
            "total_incorrect": 0,
            "machine_verifiable": mv,
            "icr": 0.0,
            "adjusted_icr": 0.0,
            "categories": {"forward_projection": 0, "growth_misattribution": 0, "genuine_error": 0},
        }

    cats = {"forward_projection": 0, "growth_misattribution": 0, "genuine_error": 0}
    for r in incorrect:
        cats[classify_incorrect_claim(r)] += 1

    n = len(incorrect)
    icr = round(n / mv, 3) if mv > 0 else 0.0
    # Adjusted ICR: only genuine errors / MV claims
    adj_icr = round(cats["genuine_error"] / mv, 3) if mv > 0 else 0.0

    return {
        "total_incorrect": n,
        "machine_verifiable": mv,
        "icr": icr,
        "adjusted_icr": adj_icr,
        "categories": {
            k: {"n": v, "pct": round(v / n * 100, 1) if n else 0}
            for k, v in cats.items()
        },
    }


def decompose_icr_from_file(ticker: str, output_dir: str = "output") -> dict:
    """Load a ticker's fact table CSV and run ICR decomposition."""
    path = Path(output_dir) / ticker / f"{ticker}_fact_table.csv"
    if not path.exists():
        return {}
    rows = []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    result = decompose_icr(rows)
    result["ticker"] = ticker
    return result


def aggregate_decomposition(tickers: list[str], output_dir: str = "output") -> dict:
    """ICR decomposition aggregated across all tickers."""
    total = {"total_incorrect": 0, "machine_verifiable": 0,
             "categories": {"forward_projection": 0, "growth_misattribution": 0, "genuine_error": 0}}
    per_ticker = {}
    for t in tickers:
        d = decompose_icr_from_file(t, output_dir)
        if not d:
            continue
        per_ticker[t] = d
        total["total_incorrect"] += d["total_incorrect"]
        total["machine_verifiable"] += d["machine_verifiable"]
        for cat in total["categories"]:
            total["categories"][cat] += d["categories"].get(cat, {}).get("n", 0) if isinstance(d["categories"].get(cat), dict) else d["categories"].get(cat, 0)

    n = total["total_incorrect"]
    total["icr"] = round(n / total["machine_verifiable"], 3) if total["machine_verifiable"] else 0.0
    total["adjusted_icr"] = round(
        total["categories"]["genuine_error"] / total["machine_verifiable"], 3
    ) if total["machine_verifiable"] else 0.0
    total["category_pcts"] = {
        k: round(v / n * 100, 1) if n else 0
        for k, v in total["categories"].items()
    }
    return {"aggregate": total, "per_ticker": per_ticker}


# ── ICR → alpha correlation ───────────────────────────────────────────────────

def icr_alpha_correlation(
    tickers: list[str],
    icr_values: dict[str, float],
    snapshot_dir: str = "output/historical_backtest",
    horizon: str = "6m",
) -> dict:
    """
    Test whether per-ticker ICR correlates with realized alpha at a given horizon.

    icr_values: dict of {ticker: icr_value} from audit runs.
    Returns Spearman rho, p-value, n, and per-observation data.

    Note: This analysis is confounded by the valuation signal — tickers with
    high ICR (loss-making companies) tend to be HOLD signals which underperform.
    See `within_signal_icr_alpha` for a controlled analysis.
    """
    snap_dir = Path(snapshot_dir)
    if not snap_dir.exists():
        return {"error": "No snapshot directory found"}

    alpha_key = f"alpha_{horizon}"
    observations = []

    for snap_path in snap_dir.glob("*_snapshot.json"):
        d = json.loads(snap_path.read_text())
        ticker = d["ticker"]
        if ticker not in icr_values:
            continue
        alpha = d.get("returns", {}).get(alpha_key)
        if alpha is None:
            continue
        observations.append({
            "ticker":   ticker,
            "cutoff":   d["cutoff_date"],
            "icr":      icr_values[ticker],
            "signal":   d["valuation"]["signal"],
            "alpha":    alpha,
            "return":   d.get("returns", {}).get(f"return_{horizon}"),
        })

    if len(observations) < 4:
        return {"error": "Insufficient data for correlation", "n": len(observations)}

    icr_list   = [o["icr"] for o in observations]
    alpha_list = [o["alpha"] for o in observations]

    result = {
        "horizon": horizon,
        "n": len(observations),
        "observations": observations,
    }

    if HAS_SCIPY:
        rho, p = spearmanr(icr_list, alpha_list)
        result["spearman_rho"]   = round(float(rho), 3)
        result["spearman_p"]     = round(float(p), 4)
        result["significant_0.05"] = bool(p < 0.05)
        result["interpretation"] = (
            "negative: lower ICR associated with better alpha" if rho < -0.3
            else "positive: higher ICR associated with better alpha (unexpected)"
            if rho > 0.3
            else "near-zero: ICR does not predict alpha at this scale"
        )

    # Within-signal analysis (controls for signal confound)
    for signal in ["buy", "hold"]:
        group = [o for o in observations if o["signal"] == signal]
        if len(group) >= 4 and HAS_SCIPY:
            rho_s, p_s = spearmanr([o["icr"] for o in group], [o["alpha"] for o in group])
            result[f"within_{signal}_rho"] = round(float(rho_s), 3)
            result[f"within_{signal}_p"]   = round(float(p_s), 4)
            result[f"within_{signal}_n"]   = len(group)

    return result


# ── Coverage analysis ─────────────────────────────────────────────────────────

def coverage_summary(tickers: list[str], output_dir: str = "output") -> dict:
    """Aggregate coverage statistics across tickers."""
    rows = []
    for t in tickers:
        sc_path = Path(output_dir) / t / f"{t}_reliability_scorecard.json"
        if not sc_path.exists():
            continue
        sc = json.loads(sc_path.read_text())
        m = sc.get("metrics", {})
        s = sc.get("summary", {})
        rows.append({
            "ticker": t,
            "total_claims": s.get("total_claims", 0),
            "mv_claims": s.get("machine_verifiable_claims", 0),
            "verified": s.get("verified_count", 0),
            "incorrect": s.get("incorrect_count", 0),
            "scr": m.get("source_coverage_rate", 0.0) or 0.0,
            "icr": m.get("incorrect_claim_rate", 0.0) or 0.0,
            "vd": m.get("valuation_dispersion"),
        })

    if not rows:
        return {}

    total_claims = sum(r["total_claims"] for r in rows)
    total_mv     = sum(r["mv_claims"] for r in rows)
    total_ver    = sum(r["verified"] for r in rows)
    total_incor  = sum(r["incorrect"] for r in rows)

    return {
        "per_ticker": rows,
        "aggregate": {
            "total_claims":       total_claims,
            "total_mv":           total_mv,
            "total_verified":     total_ver,
            "total_incorrect":    total_incor,
            "aggregate_scr":      round(total_mv / total_claims, 3) if total_claims else 0,
            "aggregate_icr":      round(total_incor / total_mv, 3) if total_mv else 0,
            "mean_scr":           round(sum(r["scr"] for r in rows) / len(rows), 3),
            "mean_icr":           round(sum(r["icr"] for r in rows) / len(rows), 3),
        },
    }
