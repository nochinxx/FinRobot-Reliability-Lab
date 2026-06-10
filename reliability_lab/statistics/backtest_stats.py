"""
Statistical analysis for the date-gated historical backtest.

Provides:
  compute_group_stats  — mean, median, std, win rate, Sharpe, max drawdown
  bootstrap_ci         — 10,000-iteration bootstrap confidence interval for mean
  mann_whitney_test    — non-parametric two-sample significance test
  welch_t_test         — parametric two-sample test (unequal variance)
  cohens_d             — effect size between two groups
  information_ratio    — mean alpha / std(alpha)
  compute_all          — full cross-group statistical summary
  format_stats_table   — markdown table for paper / paper_table.md
"""
import math
import random
from typing import Optional

try:
    from scipy import stats as _scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── Per-group statistics ───────────────────────────────────────────────────────

def compute_group_stats(returns: list[float]) -> dict:
    """
    Descriptive statistics for one group of percentage returns.

    Returns:
      n, mean, median, std, min, max, win_rate, sharpe_6m, max_drawdown
    """
    if not returns:
        return {"n": 0}

    n = len(returns)
    mean = sum(returns) / n
    sorted_r = sorted(returns)
    median = sorted_r[n // 2] if n % 2 == 1 else (sorted_r[n//2-1] + sorted_r[n//2]) / 2
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    std = math.sqrt(variance)
    win_rate = sum(1 for r in returns if r > 0) / n

    # Sharpe ratio: mean / std (no annualization — point-in-time 6m horizon)
    # Scale to annualized: multiply by sqrt(2) for 6m → annual
    sharpe_6m = (mean / std * math.sqrt(2)) if std > 0 else None

    # Pseudo-max drawdown across observations (not a time-series, so we use the
    # worst single observation as a proxy for drawdown risk)
    max_drawdown = min(returns)

    return {
        "n":            n,
        "mean":         round(mean, 2),
        "median":       round(median, 2),
        "std":          round(std, 2),
        "min":          round(min(returns), 2),
        "max":          round(max(returns), 2),
        "win_rate":     round(win_rate, 3),
        "sharpe_6m":    round(sharpe_6m, 3) if sharpe_6m is not None else None,
        "max_drawdown": round(max_drawdown, 2),
    }


def bootstrap_ci(
    returns: list[float],
    n_boot: int = 10_000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Bootstrap confidence interval for the mean of `returns`.

    Returns (lower, upper) at the given confidence level.
    Uses percentile bootstrap (Efron & Tibshirani, 1994).
    """
    if len(returns) < 2:
        m = returns[0] if returns else 0.0
        return (m, m)

    rng = random.Random(seed)
    n = len(returns)
    boot_means = []
    for _ in range(n_boot):
        sample = [rng.choice(returns) for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    alpha = (1 - ci) / 2
    lower_idx = int(alpha * n_boot)
    upper_idx = int((1 - alpha) * n_boot)
    return (round(boot_means[lower_idx], 2), round(boot_means[upper_idx], 2))


# ── Two-sample significance tests ─────────────────────────────────────────────

def mann_whitney_test(group1: list[float], group2: list[float]) -> dict:
    """
    Mann-Whitney U test (non-parametric, no normality assumption).
    Appropriate for small samples (n < 30).

    Returns: U, p_value, direction ("group1_larger" | "group2_larger" | "tied")
    Null hypothesis: distributions are identical.
    Alternative (two-tailed): one is stochastically larger.
    """
    if not group1 or not group2:
        return {"U": None, "p_value": None, "direction": None, "note": "empty group"}

    if HAS_SCIPY:
        result = _scipy_stats.mannwhitneyu(group1, group2, alternative="two-sided")
        U = float(result.statistic)
        p = float(result.pvalue)
    else:
        # Manual implementation
        U = _manual_mann_whitney_u(group1, group2)
        p = None  # Cannot compute exact p without scipy

    n1, n2 = len(group1), len(group2)
    mean1 = sum(group1) / n1
    mean2 = sum(group2) / n2
    direction = "group1_larger" if mean1 > mean2 else ("group2_larger" if mean2 > mean1 else "tied")

    return {
        "U":         round(U, 1) if U is not None else None,
        "p_value":   round(p, 4) if p is not None else None,
        "direction": direction,
        "n1":        n1,
        "n2":        n2,
        "significant_0.05": (p < 0.05) if p is not None else None,
        "significant_0.01": (p < 0.01) if p is not None else None,
    }


def _manual_mann_whitney_u(group1: list[float], group2: list[float]) -> float:
    """Manual U statistic (no p-value). Used as fallback when scipy unavailable."""
    U = 0.0
    for x in group1:
        for y in group2:
            if x > y:
                U += 1.0
            elif x == y:
                U += 0.5
    return U


def welch_t_test(group1: list[float], group2: list[float]) -> dict:
    """
    Welch's t-test (unequal variance, unequal sample size).
    More robust than Student's t for our context (n1=9, n2=15).
    """
    if not group1 or not group2 or len(group1) < 2 or len(group2) < 2:
        return {"t": None, "p_value": None, "df": None}

    if HAS_SCIPY:
        result = _scipy_stats.ttest_ind(group1, group2, equal_var=False)
        t = float(result.statistic)
        p = float(result.pvalue)
        df = float(result.df) if hasattr(result, "df") else None
    else:
        t, p, df = _manual_welch_t(group1, group2)

    return {
        "t":         round(t, 3) if t is not None else None,
        "p_value":   round(p, 4) if p is not None else None,
        "df":        round(df, 1) if df is not None else None,
        "significant_0.05": (p < 0.05) if p is not None else None,
        "significant_0.01": (p < 0.01) if p is not None else None,
    }


def _manual_welch_t(g1, g2):
    n1, n2 = len(g1), len(g2)
    m1, m2 = sum(g1)/n1, sum(g2)/n2
    v1 = sum((x-m1)**2 for x in g1)/(n1-1)
    v2 = sum((x-m2)**2 for x in g2)/(n2-1)
    if v1/n1 + v2/n2 == 0:
        return None, None, None
    t = (m1 - m2) / math.sqrt(v1/n1 + v2/n2)
    df = (v1/n1 + v2/n2)**2 / ((v1/n1)**2/(n1-1) + (v2/n2)**2/(n2-1))
    return t, None, df  # p-value needs scipy


def cohens_d(group1: list[float], group2: list[float]) -> Optional[float]:
    """
    Cohen's d effect size: (mean1 - mean2) / pooled_std.
    Interpretation: 0.2 = small, 0.5 = medium, 0.8 = large, 1.2+ = very large.
    """
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return None
    m1 = sum(group1) / n1
    m2 = sum(group2) / n2
    v1 = sum((x - m1) ** 2 for x in group1) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in group2) / (n2 - 1)
    pooled_std = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return None
    return round((m1 - m2) / pooled_std, 3)


def information_ratio(alphas: list[float]) -> Optional[float]:
    """
    Information ratio: mean(alpha) / std(alpha).
    Measures consistency of outperformance (higher = more consistent alpha).
    """
    if len(alphas) < 2:
        return None
    n = len(alphas)
    mean = sum(alphas) / n
    std = math.sqrt(sum((a - mean) ** 2 for a in alphas) / (n - 1))
    if std == 0:
        return None
    return round(mean / std, 3)


# ── Full cross-group analysis ──────────────────────────────────────────────────

def compute_all(
    snapshots: list[dict],
    horizon: str = "6m",
    ci_n_boot: int = 10_000,
) -> dict:
    """
    Full statistical analysis for BUY vs HOLD vs SELL at a given horizon.

    snapshots: list of dicts from historical_backtest snapshot files.
    horizon:   "3m", "6m", "9m", "12m"
    Returns a dict with per-group stats and cross-group significance tests.
    """
    ret_key   = f"return_{horizon}"
    alpha_key = f"alpha_{horizon}"

    by_signal: dict[str, dict] = {}
    for snap in snapshots:
        sig = snap.get("valuation", {}).get("signal", "hold")
        r   = snap.get("returns", {}).get(ret_key)
        a   = snap.get("returns", {}).get(alpha_key)
        if sig not in by_signal:
            by_signal[sig] = {"returns": [], "alphas": []}
        if r is not None:
            by_signal[sig]["returns"].append(float(r))
        if a is not None:
            by_signal[sig]["alphas"].append(float(a))

    result: dict = {"horizon": horizon, "groups": {}}

    for sig, data in by_signal.items():
        rets   = data["returns"]
        alphas = data["alphas"]
        gstats = compute_group_stats(rets)
        ci_ret = bootstrap_ci(rets, n_boot=ci_n_boot) if rets else (None, None)
        ci_alp = bootstrap_ci(alphas, n_boot=ci_n_boot) if alphas else (None, None)
        ir     = information_ratio(alphas) if alphas else None

        result["groups"][sig] = {
            **gstats,
            "ci_lower": ci_ret[0],
            "ci_upper": ci_ret[1],
            "mean_alpha":    round(sum(alphas)/len(alphas), 2) if alphas else None,
            "alpha_ci_lower": ci_alp[0],
            "alpha_ci_upper": ci_alp[1],
            "information_ratio": ir,
        }

    # Cross-group significance tests (BUY vs HOLD)
    buy_r  = by_signal.get("buy",  {}).get("returns", [])
    hold_r = by_signal.get("hold", {}).get("returns", [])
    sell_r = by_signal.get("sell", {}).get("returns", [])

    if buy_r and hold_r:
        result["buy_vs_hold"] = {
            "mann_whitney":   mann_whitney_test(buy_r, hold_r),
            "welch_t":        welch_t_test(buy_r, hold_r),
            "cohens_d":       cohens_d(buy_r, hold_r),
            "mean_diff":      round(sum(buy_r)/len(buy_r) - sum(hold_r)/len(hold_r), 2),
        }

    if buy_r and sell_r:
        result["buy_vs_sell"] = {
            "mann_whitney": mann_whitney_test(buy_r, sell_r),
            "cohens_d":     cohens_d(buy_r, sell_r),
        }

    return result


# ── Markdown table formatter ───────────────────────────────────────────────────

def format_stats_table(stats: dict) -> str:
    """
    Format full stats as a markdown table for the paper.
    stats: output of compute_all().
    """
    h = stats.get("horizon", "?")
    lines = [
        f"### Signal Performance at {h} Horizon\n",
        "| Signal | n | Mean Return | 95% CI | Median | Std | Win Rate | Sharpe | Max Drawdown | Mean Alpha | Alpha 95% CI | IR |",
        "|--------|---|-------------|--------|--------|-----|----------|--------|--------------|------------|--------------|-----|",
    ]

    for sig in ["buy", "hold", "sell"]:
        g = stats.get("groups", {}).get(sig)
        if not g or g.get("n", 0) == 0:
            continue
        ci = f"[{g['ci_lower']:+.1f}%, {g['ci_upper']:+.1f}%]" if g.get("ci_lower") is not None else "N/A"
        aci = (f"[{g['alpha_ci_lower']:+.1f}%, {g['alpha_ci_upper']:+.1f}%]"
               if g.get("alpha_ci_lower") is not None else "N/A")
        sharpe_s = f"{g['sharpe_6m']:.2f}" if g.get("sharpe_6m") is not None else "N/A"
        ir_s = f"{g['information_ratio']:.2f}" if g.get("information_ratio") is not None else "N/A"
        ma = g.get("mean_alpha")
        ma_s = f"{ma:+.1f}%" if ma is not None else "N/A"

        lines.append(
            f"| **{sig.upper()}** | {g['n']} "
            f"| **{g['mean']:+.1f}%** | {ci} "
            f"| {g['median']:+.1f}% | {g['std']:.1f}% "
            f"| {g['win_rate']:.0%} | {sharpe_s} "
            f"| {g['max_drawdown']:+.1f}% | {ma_s} | {aci} | {ir_s} |"
        )

    bvh = stats.get("buy_vs_hold")
    if bvh:
        mw  = bvh.get("mann_whitney", {})
        wt  = bvh.get("welch_t", {})
        cd  = bvh.get("cohens_d")
        md  = bvh.get("mean_diff")

        p_mw = mw.get("p_value")
        p_wt = wt.get("p_value")
        cd_interp = (
            "large" if cd and abs(cd) >= 0.8 else
            "medium" if cd and abs(cd) >= 0.5 else
            "small" if cd else "N/A"
        )
        p_str = f"p={p_mw:.4f}" if p_mw is not None else "p=N/A (scipy required)"

        lines += [
            "",
            "**BUY vs. HOLD significance tests:**",
            "",
            f"- Mean difference: {md:+.1f}pp" if md else "",
            f"- Mann-Whitney U test: {p_str}{'  ✓ significant at p<0.01' if mw.get('significant_0.01') else '  ✓ significant at p<0.05' if mw.get('significant_0.05') else ''}",
            f"- Welch's t-test: p={p_wt:.4f}" if p_wt else "- Welch's t-test: p=N/A (scipy required)",
            f"- Cohen's d: {cd:.2f} ({cd_interp} effect size)" if cd else "- Cohen's d: N/A",
            "",
            "_Note: n=27 total observations (9×BUY, 15×HOLD, 3×SELL). Bootstrap CIs use 10,000 iterations with fixed seed. "
            "Mann-Whitney U is the primary test — it makes no normality assumption, appropriate for n<30._",
        ]

    return "\n".join(l for l in lines if l is not None)
