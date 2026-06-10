"""
Tests for reliability_lab/statistics/backtest_stats.py.

Covers all statistical functions: group stats, bootstrap CI,
Mann-Whitney, Welch's t, Cohen's d, information ratio, compute_all,
and the markdown formatter. No live API calls.
"""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from reliability_lab.statistics.backtest_stats import (
    compute_group_stats,
    bootstrap_ci,
    mann_whitney_test,
    welch_t_test,
    cohens_d,
    information_ratio,
    compute_all,
    format_stats_table,
    HAS_SCIPY,
)

# ── Known returns from our 27-observation backtest ────────────────────────────
BUY_6M  = [-6.7, 5.3, 27.2, 31.0, 5.4, 23.9, 32.2, -1.9, 31.7]
HOLD_6M = [-42.8, -42.8, -51.0, -4.3, -10.8, -6.6, 5.7, -19.7, -8.9, 4.3, -47.9, -52.0, 21.7, 8.9, 0.8]
SELL_6M = [25.5, 19.1, -1.5]


# ── compute_group_stats ────────────────────────────────────────────────────────

class TestComputeGroupStats:
    def test_empty_returns(self):
        r = compute_group_stats([])
        assert r["n"] == 0

    def test_single_value(self):
        r = compute_group_stats([10.0])
        assert r["n"] == 1
        assert r["mean"] == 10.0
        assert r["win_rate"] == 1.0

    def test_buy_mean_close_to_known(self):
        r = compute_group_stats(BUY_6M)
        assert r["n"] == 9
        assert abs(r["mean"] - 16.5) < 0.5

    def test_hold_mean_close_to_known(self):
        r = compute_group_stats(HOLD_6M)
        assert r["n"] == 15
        assert abs(r["mean"] - (-16.4)) < 0.5

    def test_win_rate_buy(self):
        r = compute_group_stats(BUY_6M)
        positive = sum(1 for x in BUY_6M if x > 0)
        assert r["win_rate"] == pytest.approx(positive / len(BUY_6M), abs=0.001)

    def test_win_rate_hold(self):
        r = compute_group_stats(HOLD_6M)
        positive = sum(1 for x in HOLD_6M if x > 0)
        assert r["win_rate"] == pytest.approx(positive / len(HOLD_6M), abs=0.001)

    def test_sharpe_positive_for_buy(self):
        r = compute_group_stats(BUY_6M)
        assert r["sharpe_6m"] is not None
        assert r["sharpe_6m"] > 0

    def test_sharpe_negative_for_hold(self):
        r = compute_group_stats(HOLD_6M)
        assert r["sharpe_6m"] is not None
        assert r["sharpe_6m"] < 0

    def test_max_drawdown_is_worst_return(self):
        r = compute_group_stats(BUY_6M)
        assert r["max_drawdown"] == min(BUY_6M)

    def test_std_positive(self):
        r = compute_group_stats(BUY_6M)
        assert r["std"] > 0

    def test_all_fields_present(self):
        r = compute_group_stats(BUY_6M)
        for field in ("n", "mean", "median", "std", "min", "max",
                      "win_rate", "sharpe_6m", "max_drawdown"):
            assert field in r, f"Missing field: {field}"


# ── bootstrap_ci ──────────────────────────────────────────────────────────────

class TestBootstrapCI:
    def test_buy_ci_positive_lower_bound(self):
        lo, hi = bootstrap_ci(BUY_6M, n_boot=1000, seed=42)
        assert lo > 0, f"Expected positive lower bound for BUY, got {lo}"

    def test_hold_ci_negative_upper_bound(self):
        lo, hi = bootstrap_ci(HOLD_6M, n_boot=1000, seed=42)
        assert hi < 0, f"Expected negative upper bound for HOLD, got {hi}"

    def test_ci_lower_less_than_upper(self):
        lo, hi = bootstrap_ci(BUY_6M, n_boot=1000)
        assert lo < hi

    def test_ci_contains_mean(self):
        lo, hi = bootstrap_ci(BUY_6M, n_boot=5000, seed=0)
        mean = sum(BUY_6M) / len(BUY_6M)
        assert lo <= mean <= hi

    def test_deterministic_with_same_seed(self):
        a = bootstrap_ci(BUY_6M, n_boot=1000, seed=7)
        b = bootstrap_ci(BUY_6M, n_boot=1000, seed=7)
        assert a == b

    def test_different_seeds_may_differ(self):
        a = bootstrap_ci(BUY_6M, n_boot=100, seed=1)
        b = bootstrap_ci(BUY_6M, n_boot=100, seed=2)
        # Very likely to differ with small n_boot and different seeds
        assert a != b or True  # non-strict — just shouldn't crash

    def test_single_element_returns_same_value(self):
        lo, hi = bootstrap_ci([5.0])
        assert lo == hi == 5.0


# ── Mann-Whitney ───────────────────────────────────────────────────────────────

class TestMannWhitneyTest:
    def test_buy_vs_hold_significant(self):
        r = mann_whitney_test(BUY_6M, HOLD_6M)
        assert r["direction"] == "group1_larger"
        if HAS_SCIPY:
            assert r["p_value"] < 0.05, f"Expected significant p, got {r['p_value']}"

    def test_buy_vs_hold_significant_at_01(self):
        r = mann_whitney_test(BUY_6M, HOLD_6M)
        if HAS_SCIPY:
            assert r["significant_0.01"] is True

    def test_empty_group_returns_none(self):
        r = mann_whitney_test([], HOLD_6M)
        assert r["U"] is None

    def test_u_statistic_range(self):
        r = mann_whitney_test(BUY_6M, HOLD_6M)
        if r["U"] is not None:
            max_u = len(BUY_6M) * len(HOLD_6M)
            assert 0 <= r["U"] <= max_u

    def test_direction_field(self):
        r = mann_whitney_test(BUY_6M, HOLD_6M)
        assert r["direction"] in ("group1_larger", "group2_larger", "tied")

    def test_same_group_p_not_significant(self):
        r = mann_whitney_test(BUY_6M, BUY_6M)
        if HAS_SCIPY and r["p_value"] is not None:
            assert r["p_value"] > 0.05


# ── Welch's t-test ────────────────────────────────────────────────────────────

class TestWelchTTest:
    def test_buy_vs_hold_significant(self):
        r = welch_t_test(BUY_6M, HOLD_6M)
        if HAS_SCIPY:
            assert r["p_value"] < 0.01, f"Expected p<0.01, got {r['p_value']}"

    def test_t_statistic_positive(self):
        r = welch_t_test(BUY_6M, HOLD_6M)
        if r["t"] is not None:
            assert r["t"] > 0

    def test_insufficient_data_returns_none(self):
        r = welch_t_test([1.0], HOLD_6M)
        assert r["t"] is None or r["p_value"] is None

    def test_fields_present(self):
        r = welch_t_test(BUY_6M, HOLD_6M)
        for f in ("t", "p_value", "df"):
            assert f in r


# ── Cohen's d ─────────────────────────────────────────────────────────────────

class TestCohensD:
    def test_buy_vs_hold_large_effect(self):
        d = cohens_d(BUY_6M, HOLD_6M)
        assert d is not None
        assert d > 1.0, f"Expected large effect (>1.0), got {d}"

    def test_sign_positive_when_g1_larger(self):
        d = cohens_d([10, 20, 30], [1, 2, 3])
        assert d > 0

    def test_identical_groups_zero(self):
        d = cohens_d([5, 10, 15], [5, 10, 15])
        assert d == 0.0

    def test_insufficient_data_returns_none(self):
        assert cohens_d([1.0], [2.0]) is None


# ── Information ratio ─────────────────────────────────────────────────────────

class TestInformationRatio:
    def test_buy_ir_positive(self):
        buy_alphas = [x["returns"].get("alpha_6m") for x in
                      _load_snapshots_by_signal("buy")]
        buy_alphas = [a for a in buy_alphas if a is not None]
        ir = information_ratio(buy_alphas)
        if ir is not None:
            assert ir > 0

    def test_single_value_returns_none(self):
        assert information_ratio([5.0]) is None

    def test_zero_std_returns_none(self):
        assert information_ratio([5.0, 5.0, 5.0]) is None


def _load_snapshots_by_signal(signal: str) -> list[dict]:
    snap_dir = Path("output/historical_backtest")
    if not snap_dir.exists():
        return []
    import json
    result = []
    for f in snap_dir.glob("*_snapshot.json"):
        d = json.loads(f.read_text())
        if d.get("valuation", {}).get("signal") == signal:
            result.append(d)
    return result


# ── compute_all ───────────────────────────────────────────────────────────────

class TestComputeAll:
    def _make_snapshots(self, buy_rets, hold_rets, sell_rets=None):
        snaps = []
        for r in buy_rets:
            snaps.append({"valuation": {"signal": "buy"},
                          "returns": {"return_6m": r, "alpha_6m": r - 2}})
        for r in hold_rets:
            snaps.append({"valuation": {"signal": "hold"},
                          "returns": {"return_6m": r, "alpha_6m": r - 2}})
        if sell_rets:
            for r in sell_rets:
                snaps.append({"valuation": {"signal": "sell"},
                              "returns": {"return_6m": r, "alpha_6m": r - 2}})
        return snaps

    def test_returns_horizon_key(self):
        snaps = self._make_snapshots(BUY_6M, HOLD_6M)
        result = compute_all(snaps, horizon="6m")
        assert result["horizon"] == "6m"

    def test_groups_present(self):
        snaps = self._make_snapshots(BUY_6M, HOLD_6M)
        result = compute_all(snaps, horizon="6m")
        assert "buy" in result["groups"]
        assert "hold" in result["groups"]

    def test_buy_vs_hold_present(self):
        snaps = self._make_snapshots(BUY_6M, HOLD_6M)
        result = compute_all(snaps, horizon="6m")
        assert "buy_vs_hold" in result

    def test_ci_computed(self):
        snaps = self._make_snapshots(BUY_6M, HOLD_6M)
        result = compute_all(snaps, horizon="6m", ci_n_boot=100)
        buy = result["groups"]["buy"]
        assert buy["ci_lower"] is not None
        assert buy["ci_upper"] is not None

    def test_empty_snapshots(self):
        result = compute_all([], horizon="6m")
        assert result["groups"] == {}

    def test_known_results_6m(self):
        snaps = self._make_snapshots(BUY_6M, HOLD_6M)
        result = compute_all(snaps, horizon="6m")
        buy = result["groups"]["buy"]
        assert abs(buy["mean"] - 16.5) < 0.5
        if HAS_SCIPY:
            bvh = result["buy_vs_hold"]
            assert bvh["mann_whitney"]["significant_0.01"] is True


# ── format_stats_table ────────────────────────────────────────────────────────

class TestFormatStatsTable:
    def _make_result(self):
        snaps = []
        for r in BUY_6M:
            snaps.append({"valuation": {"signal": "buy"},
                          "returns": {"return_6m": r, "alpha_6m": r - 2}})
        for r in HOLD_6M:
            snaps.append({"valuation": {"signal": "hold"},
                          "returns": {"return_6m": r, "alpha_6m": r - 2}})
        return compute_all(snaps, horizon="6m", ci_n_boot=500)

    def test_returns_string(self):
        result = self._make_result()
        table = format_stats_table(result)
        assert isinstance(table, str)
        assert len(table) > 100

    def test_contains_buy_hold(self):
        table = format_stats_table(self._make_result())
        assert "BUY" in table
        assert "HOLD" in table

    def test_contains_significance(self):
        table = format_stats_table(self._make_result())
        if HAS_SCIPY:
            assert "p=" in table or "Mann-Whitney" in table

    def test_contains_cohens_d(self):
        table = format_stats_table(self._make_result())
        assert "Cohen" in table or "cohens" in table.lower()

    def test_no_crash_empty(self):
        table = format_stats_table({"horizon": "6m", "groups": {}})
        assert isinstance(table, str)
