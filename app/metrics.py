"""Measurement (blueprint 6, 10.4, 16): hit rate with Wilson CI, profit factor, drawdown, calibration, test verdict."""
from __future__ import annotations

from math import sqrt

# Blueprint 5.2 - results from the video, shown next to live results in the version table.
HISTORICAL_VERSIONS = [
    {"version": "V1", "closed": None, "wins": None, "hit": None, "pnl_sol": None, "note": "single agent, 2 duplicated losses"},
    {"version": "V2", "closed": 41, "wins": 17, "hit": 0.41, "pnl_sol": -0.0209, "note": "41 across four tests"},
    {"version": "V3", "closed": 20, "wins": 7, "hit": 0.35, "pnl_sol": -0.0213, "note": "20 across two tests"},
    {"version": "V4", "closed": 20, "wins": 7, "hit": 0.35, "pnl_sol": -0.0229, "note": "20 across two tests"},
    {"version": "V5", "closed": 49, "wins": 26, "hit": 0.53, "pnl_sol": -0.0954, "note": "baseline + continuous test"},
    {"version": "V6", "closed": 7, "wins": 4, "hit": 0.57, "pnl_sol": -0.0234, "note": "7 of 20 planned"},
    {"version": "V7 (video)", "closed": 10, "wins": 8, "hit": 0.80, "pnl_sol": 0.0438, "note": "10 of 100 planned"},
]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def max_drawdown(pnls: list[float]) -> float:
    """Largest peak-to-trough fall of the cumulative PnL curve (SOL, positive number)."""
    peak = eq = dd = 0.0
    for x in pnls:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def summary(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "wins": 0, "hit": 0.0, "ci95": (0.0, 0.0), "pnl_sol": 0.0, "profit_factor": None,
                "avg_win_pct": None, "avg_loss_pct": None, "breakeven_hit": None, "worst_pct": None,
                "best_pct": None, "max_dd_sol": 0.0, "avg_return_pct": None, "avg_hold_min": None,
                "exit_reasons": {}, "max_profit_share": None}
    wins = [t for t in trades if (t["return_pct"] or 0) > 0]
    losses = [t for t in trades if (t["return_pct"] or 0) <= 0]
    gw = sum(t["pnl_sol"] for t in trades if t["pnl_sol"] > 0)
    gl = -sum(t["pnl_sol"] for t in trades if t["pnl_sol"] <= 0)
    avg_win = sum(t["return_pct"] for t in wins) / len(wins) if wins else None
    avg_loss = -sum(t["return_pct"] for t in losses) / len(losses) if losses else None
    breakeven = (avg_loss / (avg_win + avg_loss)) if (avg_win and avg_loss is not None and avg_win + avg_loss > 0) else None
    pnl = sum(t["pnl_sol"] for t in trades)
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.get("exit_reason") or "?"] = reasons.get(t.get("exit_reason") or "?", 0) + 1
    holds = [(t["closed_at"] - t["opened_at"]) / 60 for t in trades if t.get("closed_at") and t.get("opened_at")]
    best_pnl = max((t["pnl_sol"] for t in trades), default=0.0)
    return {
        "n": n,
        "wins": len(wins),
        "hit": len(wins) / n,
        "ci95": wilson(len(wins), n),
        "pnl_sol": pnl,
        "profit_factor": (gw / gl) if gl > 0 else (float("inf") if gw > 0 else None),
        "avg_win_pct": avg_win,
        "avg_loss_pct": -avg_loss if avg_loss is not None else None,
        "breakeven_hit": breakeven,
        "worst_pct": min(t["return_pct"] for t in trades),
        "best_pct": max(t["return_pct"] for t in trades),
        "avg_return_pct": sum(t["return_pct"] for t in trades) / n,
        "max_dd_sol": max_drawdown([t["pnl_sol"] for t in trades]),
        "avg_hold_min": sum(holds) / len(holds) if holds else None,
        "exit_reasons": reasons,
        "max_profit_share": (best_pnl / pnl) if pnl > 0 else None,
    }


def calibration(trades: list[dict], take_profit_pct: float,
                buckets=((0, 69), (70, 79), (80, 89), (90, 100))) -> dict:
    """Does a higher Confidence Score actually mean better trades? (blueprint 10.4)"""
    out = {}
    for a, b in buckets:
        sub = [t for t in trades if a <= (t.get("confidence") or 0) <= b]
        s = summary(sub)
        out[f"{a}-{b}"] = {"n": s["n"], "hit": s["hit"], "avg_return_pct": s["avg_return_pct"], "pnl_sol": s["pnl_sol"]}
    scored = [t for t in trades if t.get("confidence") is not None]
    if scored:
        # Brier score of "reached +TP before the stop": score/100 is the agents' implied probability.
        def hit_tp(t):
            return 1.0 if (t.get("exit_reason") == "TP" or (t.get("peak_return_pct") or 0) >= take_profit_pct) else 0.0
        out["brier_tp"] = sum(((t["confidence"] / 100) - hit_tp(t)) ** 2 for t in scored) / len(scored)
        out["base_rate_tp"] = sum(hit_tp(t) for t in scored) / len(scored)
    return out


def evaluate_test(trades: list[dict], cfg: dict, operating_cost_usd: float, sol_usd: float | None) -> dict:
    """Blueprint 16.2 success conditions (all required) and 16.3 early-stop rules."""
    t = cfg["test"]
    capital = cfg["sizing"]["paper_capital_sol"]
    s = summary(trades)
    cal = calibration(trades, cfg["exits"]["take_profit_pct"])
    planned = t["planned_trades"]
    done = s["n"] >= planned
    crit = []

    def add(name, ok, detail):
        crit.append({"name": name, "status": ("pass" if ok else "fail") if ok is not None else "pending", "detail": detail})

    lo = s["ci95"][0]
    be = s["breakeven_hit"]
    add("Wilson 95% lower bound > breakeven hit rate",
        (lo > be) if (be is not None and s["n"] >= 10) else None,
        f"lower {lo:.0%} vs breakeven {be:.0%}" if be is not None else "needs wins and losses")
    pf = s["profit_factor"]
    add(f"Profit factor after costs >= {t['min_profit_factor']}",
        (pf >= t["min_profit_factor"]) if (pf is not None and s["n"] >= 10) else None,
        f"PF {pf:.2f}" if pf not in (None, float("inf")) else f"PF {pf}")
    dd_pct = s["max_dd_sol"] / capital * 100 if capital else 0
    add(f"Max drawdown <= {t['max_drawdown_pct_of_capital']}% of paper capital",
        dd_pct <= t["max_drawdown_pct_of_capital"], f"{dd_pct:.1f}% of {capital} SOL")
    share = s["max_profit_share"]
    add(f"No single trade > {t['max_single_trade_profit_share']:.0%} of profit",
        (share <= t["max_single_trade_profit_share"]) if (share is not None and s["n"] >= 10) else None,
        f"largest trade = {share:.0%} of profit" if share is not None else "no net profit yet")
    hi, lo_b = cal.get("80-89", {}), cal.get("70-79", {})
    hi_n = hi.get("n", 0) + cal.get("90-100", {}).get("n", 0)
    hi_ret = None
    if hi_n:
        hi_ret = ((hi.get("avg_return_pct") or 0) * hi.get("n", 0) +
                  (cal.get("90-100", {}).get("avg_return_pct") or 0) * cal.get("90-100", {}).get("n", 0)) / hi_n
    add("Calibration: score 80+ beats 70-79",
        (hi_ret > lo_b["avg_return_pct"]) if (hi_n >= 5 and lo_b.get("n", 0) >= 5) else None,
        (f"80+: {hi_ret:+.1f}% avg (n={hi_n}) vs 70-79: {lo_b['avg_return_pct']:+.1f}% (n={lo_b['n']})"
         if hi_ret is not None and lo_b.get("avg_return_pct") is not None else "needs >= 5 trades in each bucket"))
    pnl_usd = s["pnl_sol"] * sol_usd if sol_usd else None
    add("Operating costs (LLM + X + RPC + hosting) < paper profit",
        (operating_cost_usd < pnl_usd) if (pnl_usd is not None and s["n"] >= 10) else None,
        f"costs ${operating_cost_usd:.2f} vs profit ${pnl_usd:.2f}" if pnl_usd is not None else f"costs ${operating_cost_usd:.2f}")

    early = []
    if s["n"] >= t["early_stop_min_trades"] and pf is not None and pf < t["early_stop_profit_factor"]:
        early.append(f"PF {pf:.2f} < {t['early_stop_profit_factor']} after {s['n']} trades")
    if capital and s["max_dd_sol"] / capital * 100 > t["early_stop_drawdown_pct"]:
        early.append(f"drawdown {dd_pct:.0f}% > {t['early_stop_drawdown_pct']}%")

    statuses = {c["status"] for c in crit}
    if early:
        verdict = "STOPPED EARLY"
    elif not done:
        verdict = "IN PROGRESS"
    elif "fail" in statuses:
        verdict = "FAILED"
    elif "pending" in statuses:
        verdict = "INCONCLUSIVE"  # nothing failed, but at least one condition never got enough data to judge
    else:
        verdict = "PASSED"
    return {"summary": s, "calibration": cal, "criteria": crit, "early_stop": early, "verdict": verdict,
            "progress": min(s["n"], planned), "planned": planned}


def jsonable(x):
    """Make metrics JSON-safe (inf/tuples)."""
    if isinstance(x, float):
        if x == float("inf"):
            return "inf"
        return round(x, 6)
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    return x
