"""Scoring system for Agent League.

Pure functions -- no state, no DB dependency. Just math.

Two entry points:
  calculate_scores()  - per-agent metrics from trade history
  rank_agents()       - normalize + rank across all agents
"""

from __future__ import annotations

import math
import statistics
from typing import Any


# ---------------------------------------------------------------------------
# Per-agent scoring
# ---------------------------------------------------------------------------

def calculate_scores(
    trades: list[dict[str, Any]],
    current_value: float,
    starting_value: float = 10_000.0,
) -> dict[str, float | int]:
    """Compute performance metrics for a single agent.

    Parameters
    ----------
    trades:
        Chronological list of trade dicts.  Each dict is expected to contain
        at least ``action`` (str) and ``portfolio_value_after`` (float).
    current_value:
        The agent's current total portfolio value.
    starting_value:
        The value the agent started the season with (default 10 000).

    Returns
    -------
    dict with keys: pnl_pct, sharpe_ratio, win_rate, max_drawdown_pct,
    total_trades, composite_score (raw, un-normalized).
    """

    # -- PnL % ---------------------------------------------------------------
    if starting_value == 0:
        pnl_pct = 0.0
    else:
        pnl_pct = (current_value - starting_value) / starting_value * 100.0

    # -- Collect portfolio value series ---------------------------------------
    values: list[float] = [
        t["portfolio_value_after"]
        for t in trades
        if "portfolio_value_after" in t
    ]

    # -- Sharpe ratio ---------------------------------------------------------
    sharpe_ratio = _sharpe(values)

    # -- Win rate -------------------------------------------------------------
    win_rate = _win_rate(trades)

    # -- Max drawdown ---------------------------------------------------------
    max_drawdown_pct = _max_drawdown(values)

    # -- Total trades (non-hold) ---------------------------------------------
    total_trades = sum(
        1 for t in trades if t.get("action", "hold") != "hold"
    )

    # -- Composite (raw, un-normalized) --------------------------------------
    # The real composite is computed in rank_agents() after cross-agent
    # normalization.  Here we store the raw ingredients so the caller can
    # inspect them; the composite_score field is set to 0.0 as a placeholder.
    composite_score = 0.0

    return {
        "pnl_pct": round(pnl_pct, 4),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "win_rate": round(win_rate, 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
        "total_trades": total_trades,
        "composite_score": composite_score,
    }


# ---------------------------------------------------------------------------
# Cross-agent ranking
# ---------------------------------------------------------------------------

def rank_agents(all_scores: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize metrics across agents, compute composite, sort, and rank.

    Parameters
    ----------
    all_scores:
        Mapping of ``agent_id`` -> output of :func:`calculate_scores`.

    Returns
    -------
    List of dicts sorted by composite_score descending, each containing:
    agent_id, rank, pnl_pct, sharpe_ratio, win_rate, max_drawdown_pct,
    total_trades, composite_score.
    """

    if not all_scores:
        return []

    agent_ids = list(all_scores.keys())

    # Gather raw metric vectors -----------------------------------------------
    pnl_vals = [all_scores[a]["pnl_pct"] for a in agent_ids]
    sharpe_vals = [all_scores[a]["sharpe_ratio"] for a in agent_ids]
    win_vals = [all_scores[a]["win_rate"] for a in agent_ids]
    dd_vals = [all_scores[a]["max_drawdown_pct"] for a in agent_ids]

    # Normalize each metric to [0, 1] ----------------------------------------
    norm_pnl = _normalize(pnl_vals)
    norm_sharpe = _normalize(sharpe_vals)
    norm_win = _normalize(win_vals)
    norm_dd = _normalize(dd_vals)

    # Composite: drawdown is subtracted (lower is better) ---------------------
    results: list[dict[str, Any]] = []
    for i, aid in enumerate(agent_ids):
        composite = (
            0.40 * norm_pnl[i]
            + 0.25 * norm_sharpe[i]
            + 0.15 * norm_win[i]
            - 0.20 * norm_dd[i]
        )
        results.append({
            "agent_id": aid,
            "pnl_pct": all_scores[aid]["pnl_pct"],
            "sharpe_ratio": all_scores[aid]["sharpe_ratio"],
            "win_rate": all_scores[aid]["win_rate"],
            "max_drawdown_pct": all_scores[aid]["max_drawdown_pct"],
            "total_trades": all_scores[aid]["total_trades"],
            "composite_score": round(composite, 6),
        })

    # Sort descending by composite_score, then by pnl_pct as tiebreaker ------
    results.sort(key=lambda r: (r["composite_score"], r["pnl_pct"]), reverse=True)

    # Assign ranks (1-based) --------------------------------------------------
    for rank, entry in enumerate(results, start=1):
        entry["rank"] = rank

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sharpe(values: list[float]) -> float:
    """Annualized-ish Sharpe from a portfolio value series.

    Returns 0.0 when there are fewer than 3 data points or when std == 0.
    """
    if len(values) < 3:
        return 0.0

    returns: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev == 0:
            returns.append(0.0)
        else:
            returns.append((values[i] - prev) / prev)

    if len(returns) < 2:
        return 0.0

    std = statistics.stdev(returns)
    if std == 0:
        return 0.0

    mean_ret = statistics.mean(returns)
    n = len(returns)
    return mean_ret / std * math.sqrt(n)


def _win_rate(trades: list[dict[str, Any]]) -> float:
    """Percentage of non-hold trades that increased portfolio value.

    A trade is considered "winning" when its ``portfolio_value_after`` is
    strictly greater than the previous trade's ``portfolio_value_after``
    (or the implicit starting value for the first trade).
    """
    non_hold = [t for t in trades if t.get("action", "hold") != "hold"]
    if not non_hold:
        return 0.0

    wins = 0
    # Build a mapping from trade index in the original list to the previous
    # portfolio value so that we can compare before/after.
    prev_value: float | None = None
    for t in trades:
        current_val = t.get("portfolio_value_after")
        if t.get("action", "hold") != "hold":
            if prev_value is not None and current_val is not None:
                if current_val > prev_value:
                    wins += 1
            # If this is the very first trade and there's no previous value,
            # we can't determine win/loss -- skip it.
        if current_val is not None:
            prev_value = current_val

    return wins / len(non_hold) * 100.0


def _max_drawdown(values: list[float]) -> float:
    """Maximum peak-to-trough decline (%) in a value series."""
    if not values:
        return 0.0

    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _normalize(vals: list[float]) -> list[float]:
    """Min-max normalize a list of floats to [0, 1].

    Returns all zeros if max == min (all values identical).
    """
    if not vals:
        return []
    lo = min(vals)
    hi = max(vals)
    if hi == lo:
        return [0.0] * len(vals)
    return [(v - lo) / (hi - lo) for v in vals]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Agent League Scoring -- Self-Test")
    print("=" * 60)

    # --- Agent A: Steady winner ---
    trades_a = [
        {"action": "buy",  "portfolio_value_after": 10_200},
        {"action": "buy",  "portfolio_value_after": 10_500},
        {"action": "sell", "portfolio_value_after": 10_800},
        {"action": "hold", "portfolio_value_after": 10_800},
        {"action": "buy",  "portfolio_value_after": 11_000},
        {"action": "sell", "portfolio_value_after": 11_300},
    ]
    scores_a = calculate_scores(trades_a, current_value=11_300, starting_value=10_000)
    print(f"\nAgent A (Steady winner): {scores_a}")

    # --- Agent B: Volatile but profitable ---
    trades_b = [
        {"action": "buy",  "portfolio_value_after": 10_500},
        {"action": "sell", "portfolio_value_after": 9_800},
        {"action": "buy",  "portfolio_value_after": 10_800},
        {"action": "sell", "portfolio_value_after": 9_500},
        {"action": "buy",  "portfolio_value_after": 11_500},
        {"action": "sell", "portfolio_value_after": 10_700},
    ]
    scores_b = calculate_scores(trades_b, current_value=10_700, starting_value=10_000)
    print(f"Agent B (Volatile):      {scores_b}")

    # --- Agent C: Steady loser ---
    trades_c = [
        {"action": "buy",  "portfolio_value_after": 9_900},
        {"action": "sell", "portfolio_value_after": 9_700},
        {"action": "buy",  "portfolio_value_after": 9_500},
        {"action": "sell", "portfolio_value_after": 9_300},
        {"action": "hold", "portfolio_value_after": 9_300},
        {"action": "sell", "portfolio_value_after": 9_000},
    ]
    scores_c = calculate_scores(trades_c, current_value=9_000, starting_value=10_000)
    print(f"Agent C (Steady loser):  {scores_c}")

    # --- Rank them ---
    all_scores = {
        "agent-a": scores_a,
        "agent-b": scores_b,
        "agent-c": scores_c,
    }
    rankings = rank_agents(all_scores)

    print("\n" + "-" * 60)
    print("LEADERBOARD")
    print("-" * 60)
    for entry in rankings:
        print(
            f"  #{entry['rank']}  {entry['agent_id']:<12}  "
            f"PnL={entry['pnl_pct']:+.2f}%  "
            f"Sharpe={entry['sharpe_ratio']:.3f}  "
            f"WinRate={entry['win_rate']:.1f}%  "
            f"MaxDD={entry['max_drawdown_pct']:.2f}%  "
            f"Trades={entry['total_trades']}  "
            f"Composite={entry['composite_score']:.4f}"
        )

    # --- Edge cases ---
    print("\n" + "-" * 60)
    print("EDGE CASES")
    print("-" * 60)

    empty = calculate_scores([], current_value=10_000, starting_value=10_000)
    print(f"  Empty trades:      {empty}")

    single = calculate_scores(
        [{"action": "buy", "portfolio_value_after": 10_100}],
        current_value=10_100,
    )
    print(f"  Single trade:      {single}")

    all_hold = calculate_scores(
        [
            {"action": "hold", "portfolio_value_after": 10_000},
            {"action": "hold", "portfolio_value_after": 10_000},
        ],
        current_value=10_000,
    )
    print(f"  All holds:         {all_hold}")

    # All agents tied
    tied = rank_agents({
        "x": calculate_scores([], current_value=10_000),
        "y": calculate_scores([], current_value=10_000),
    })
    print(f"  Tied agents:       {[(e['agent_id'], e['rank']) for e in tied]}")

    print("\n" + "=" * 60)
    print("Self-test complete.")
