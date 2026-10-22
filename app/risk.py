"""Entry guards: open-position cap, daily loss limit, per-coin cooldown, kill switch, early-stop halt."""
from __future__ import annotations

import time
from datetime import datetime, timezone


def utc_midnight(ts: float | None = None) -> int:
    d = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    return int(d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


class RiskManager:
    def __init__(self, cfg: dict, db):
        self.cfg, self.db = cfg, db

    async def kill_switch_until(self) -> int | None:
        r = self.cfg["risk"]
        n = r["kill_switch_consecutive_losses"]
        if n <= 0:
            return None
        last = (await self.db.closed_positions(limit=n))
        if len(last) < n or not all((t["return_pct"] or 0) <= r["kill_switch_loss_pct"] for t in last):
            return None
        until = int(last[-1]["closed_at"] + r["kill_switch_pause_hours"] * 3600)
        return until if until > time.time() else None

    async def can_open(self, mint: str) -> tuple[bool, str]:
        s, r = self.cfg["sizing"], self.cfg["risk"]
        if await self.db.meta_get("paused", False):
            return False, "paused by operator"
        halted = await self.db.meta_get(f"halted:{self.cfg['version']}")
        if halted and r.get("auto_stop_on_early_stop_rule", True):
            return False, f"test halted: {halted}"
        if await self.db.has_open(mint):
            return False, "already holding this coin"
        if await self.db.open_count() >= s["max_open_positions"]:
            return False, f"max open positions ({s['max_open_positions']})"
        today = await self.db.realized_since(utc_midnight())
        if today <= -s["max_daily_loss_sol"]:
            return False, f"daily loss limit hit ({today:+.4f} SOL)"
        last_exit = await self.db.last_exit_ts(mint)
        if last_exit and time.time() - last_exit < r["cooldown_minutes_after_exit"] * 60:
            return False, "cooldown after recent exit on this coin"
        until = await self.kill_switch_until()
        if until:
            return False, f"kill switch: {r['kill_switch_consecutive_losses']} losses in a row, paused until " \
                          f"{datetime.fromtimestamp(until, tz=timezone.utc):%H:%M} UTC"
        return True, "ok"
