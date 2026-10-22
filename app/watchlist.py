"""Discovery scheduling: which tokens to (re)check against the hard filter, and when.

pump.fun launches start on a bonding curve and only become tradeable (liquidity >= $10k) minutes later,
often at migration. So every discovered token is re-checked on a backoff schedule instead of once.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

PRIORITY = {"migrate": 0, "boost": 1, "profile": 1, "create": 2, "demo": 1}


@dataclass
class Entry:
    mint: str
    symbol: str | None
    source: str
    first_seen: float
    next_check: float
    checks: int = 0
    hot: bool = False
    history: deque = field(default_factory=lambda: deque(maxlen=8))


class Watchlist:
    def __init__(self, cfg: dict):
        self.d = cfg["discovery"]
        self.max_age_s = cfg["filters"]["max_age_minutes"] * 60
        self.entries: dict[str, Entry] = {}
        self.dropped_full = 0

    def __len__(self) -> int:
        return len(self.entries)

    def add(self, mint: str, symbol: str | None, source: str, now: float | None = None) -> bool:
        now = now or time.time()
        e = self.entries.get(mint)
        hot = source in ("migrate", "boost", "profile", "demo")
        if e:
            if hot and not e.hot:  # promote a bonding-curve token that just migrated / got a profile
                e.hot, e.source = True, source
                e.next_check = min(e.next_check, now)
            return False
        if len(self.entries) >= self.d["max_watchlist"]:
            if not self._evict(now):
                self.dropped_full += 1
                return False
        first = self.d["new_token_first_check_minutes"] * 60 if not hot else 0
        self.entries[mint] = Entry(mint, symbol, source, now, now + first, hot=hot)
        return True

    def _evict(self, now: float) -> bool:
        cold = [e for e in self.entries.values() if not e.hot]
        if not cold:
            return False
        victim = min(cold, key=lambda e: e.first_seen)
        del self.entries[victim.mint]
        return True

    def due(self, n: int, now: float | None = None) -> list[Entry]:
        now = now or time.time()
        ready = [e for e in self.entries.values() if e.next_check <= now]
        ready.sort(key=lambda e: (PRIORITY.get(e.source, 3), e.next_check))
        return ready[:n]

    def checked(self, mint: str, snap: dict | None, now: float | None = None) -> None:
        """Reschedule (or drop) after a check."""
        now = now or time.time()
        e = self.entries.get(mint)
        if not e:
            return
        e.checks += 1
        if snap:
            e.symbol = snap.get("symbol") or e.symbol
            e.history.append({"t": now, "price": snap["price_usd"], "liq": snap["liquidity_usd"],
                              "vol_m5": snap["vol_m5"], "buys_m5": snap["buys_m5"], "sells_m5": snap["sells_m5"]})
            age_s = (snap.get("age_min") or 0) * 60
            if age_s > self.max_age_s:
                del self.entries[mint]
                return
        if now - e.first_seen > self.max_age_s + 3600:
            del self.entries[mint]
            return
        if e.hot:
            e.next_check = now + self.d["migration_recheck_seconds"]
            return
        sched = self.d["recheck_schedule_minutes"]
        if e.checks >= len(sched):
            del self.entries[mint]
            return
        e.next_check = e.first_seen + sched[e.checks] * 60
        if e.next_check <= now:
            e.next_check = now + 30

    def trend(self, mint: str) -> list[dict]:
        e = self.entries.get(mint)
        if not e:
            return []
        now = time.time()
        return [{"min_ago": round((now - h["t"]) / 60, 1), **{k: v for k, v in h.items() if k != "t"}} for h in e.history]

    def stats(self) -> dict:
        hot = sum(1 for e in self.entries.values() if e.hot)
        return {"size": len(self.entries), "hot": hot, "cold": len(self.entries) - hot, "dropped_full": self.dropped_full}
