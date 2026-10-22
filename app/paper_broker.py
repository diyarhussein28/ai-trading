"""Paper broker (blueprint 12.6): realistic fills, TP / SL / trailing / time stop / rug exit.

Live execution is intentionally NOT implemented (blueprint 12 + 17): the system must pass the 100-trade
paper test first, and a live executor needs its own review (Jupiter quote/swap, priority fees, MEV
protection, max slippage, fill verification, separate hot wallet).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass


class LiveTradingNotImplemented(RuntimeError):
    pass


def assert_paper_mode(cfg: dict) -> None:
    if cfg["mode"] == "live":
        if os.environ.get("ALLOW_LIVE") != "yes":
            raise LiveTradingNotImplemented("mode: live requires ALLOW_LIVE=yes (blueprint 17.2).")
        raise LiveTradingNotImplemented(
            "Live execution is not implemented. Pass the 100-trade paper test (section 16.2) first, "
            "then add a reviewed executor (section 17.1).")


def cost_rate(cfg: dict) -> float:
    c = cfg["costs"]
    return (c["fee_pct_per_side"] + c["slippage_pct_per_side"]) / 100


def price_impact(cfg: dict, size_sol: float, sol_usd: float | None, liquidity_usd: float) -> float:
    """Constant-product AMM: impact ~ trade / quote-side reserve ~ 2 * size_usd / total liquidity."""
    if not cfg["costs"].get("model_price_impact") or not sol_usd or liquidity_usd <= 0:
        return 0.0
    return min(0.5, 2 * size_sol * sol_usd / liquidity_usd)


def entry_fill(cfg: dict, mid: float, size_sol: float, sol_usd: float | None, liq: float) -> float:
    return mid * (1 + cost_rate(cfg) + price_impact(cfg, size_sol, sol_usd, liq))


def exit_fill(cfg: dict, mid: float, size_sol: float, sol_usd: float | None, liq: float) -> float:
    return mid * max(0.0, 1 - cost_rate(cfg) - price_impact(cfg, size_sol, sol_usd, liq))


@dataclass
class ExitSignal:
    reason: str
    price: float
    peak: float


def evaluate_exit(pos: dict, snap: dict | None, cfg: dict, now: float, sol_usd: float | None) -> tuple[ExitSignal | None, dict]:
    """Pure exit logic. Returns (exit or None, fields to persist on the position)."""
    ex = cfg["exits"]
    peak = float(pos.get("peak_return_pct") or 0.0)
    held_min = (now - pos["opened_at"]) / 60

    if snap is None or snap.get("price_usd", 0) <= 0:
        missing = int(pos.get("missing_polls") or 0) + 1
        if missing >= ex["missing_data_polls_before_rug_exit"]:
            last = pos.get("last_price") or pos["entry_mid_price"]
            px = last * (1 - ex["missing_data_exit_haircut_pct"] / 100) * (1 - cost_rate(cfg))
            return ExitSignal("RUG", px, peak), {"missing_polls": missing}
        if held_min >= ex["time_stop_minutes"] * 2:  # never hold a position blind forever
            last = pos.get("last_price") or pos["entry_mid_price"]
            return ExitSignal("TIME", exit_fill(cfg, last, pos["size_sol"], sol_usd, pos.get("last_liq") or 1), peak), {}
        return None, {"missing_polls": missing}

    mid, liq = snap["price_usd"], snap["liquidity_usd"]
    upd = {"last_price": mid, "last_liq": liq, "missing_polls": 0}
    if liq < pos["entry_liq"] * (1 - ex["rug_liquidity_drop_pct"] / 100):
        # Liquidity pulled: we are selling into a collapsing pool - assume 3x the normal friction.
        px = mid * max(0.0, 1 - 3 * cost_rate(cfg) - price_impact(cfg, pos["size_sol"], sol_usd, liq))
        return ExitSignal("RUG", px, peak), upd

    bid = exit_fill(cfg, mid, pos["size_sol"], sol_usd, liq)
    ret = (bid / pos["entry_price"] - 1) * 100
    peak = max(peak, ret)
    upd["peak_return_pct"] = peak
    if ret >= ex["take_profit_pct"]:
        return ExitSignal("TP", bid, peak), upd
    if ret <= ex["stop_loss_pct"]:
        return ExitSignal("SL", bid, peak), upd
    t = ex["trailing"]
    if peak >= t["activate_at_pct"] and ret <= peak - t["trail_pct"]:
        return ExitSignal("TRAIL", bid, peak), upd
    if held_min >= ex["time_stop_minutes"]:
        return ExitSignal("TIME", bid, peak), upd
    return None, upd


class PaperBroker:
    def __init__(self, cfg: dict, db):
        assert_paper_mode(cfg)
        self.cfg, self.db = cfg, db

    async def open(self, snap: dict, size_sol: float, score: int, decision_id: int, sol_usd: float | None) -> dict | None:
        mid, liq = snap["price_usd"], snap["liquidity_usd"]
        return await self.db.insert_position(
            mint=snap["mint"], symbol=snap.get("symbol"), version=self.cfg["version"], decision_id=decision_id,
            confidence=score, size_sol=size_sol, opened_at=int(time.time()), closed_at=None,
            entry_price=entry_fill(self.cfg, mid, size_sol, sol_usd, liq), entry_mid_price=mid, entry_liq=liq,
            last_price=mid, last_liq=liq, mode="paper", config_hash=self.cfg["_meta"]["hash"])

    async def check(self, pos: dict, snap: dict | None, sol_usd: float | None) -> dict | None:
        """Mark one position to market; close it if an exit fires. Returns the closed row or None."""
        sig, upd = evaluate_exit(pos, snap, self.cfg, time.time(), sol_usd)
        if sig is None:
            if upd:
                await self.db.update_position_mark(pos["id"], **upd)
            return None
        if upd:
            await self.db.update_position_mark(pos["id"], **{k: v for k, v in upd.items() if k != "peak_return_pct"})
        return await self.close(pos, sig.price, sig.reason, sig.peak)

    async def close(self, pos: dict, px: float, reason: str, peak: float | None) -> dict | None:
        r = px / pos["entry_price"] - 1
        net_fee = 2 * self.cfg["costs"]["network_fee_sol"]
        pnl = pos["size_sol"] * r - net_fee
        fees = pos["size_sol"] * cost_rate(self.cfg) * 2 + net_fee
        return await self.db.close_position(pos["id"], px, r * 100, pnl, fees, reason, peak, int(time.time()))
