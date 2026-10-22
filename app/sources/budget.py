"""SpendGuard (blueprint 11.3): hard hourly/daily USD caps so a data source can never repeat the -$40-in-12-minutes event."""
from __future__ import annotations

import time


class SpendGuard:
    def __init__(self, db, hourly_usd: float, daily_usd: float):
        self.db, self.h, self.d = db, hourly_usd, daily_usd

    async def allow(self, service: str, est_usd: float) -> bool:
        now = int(time.time())
        spent_h = await self.db.spend_since(service, now - 3600)
        spent_d = await self.db.spend_since(service, now - 86400)
        return spent_h + est_usd <= self.h and spent_d + est_usd <= self.d

    async def record(self, service: str, units: int, usd: float, note: str = "") -> None:
        await self.db.insert_spend(service, units, usd, note)

    async def status(self, service: str) -> dict:
        now = int(time.time())
        h = await self.db.spend_since(service, now - 3600)
        d = await self.db.spend_since(service, now - 86400)
        return {"hour_usd": round(h, 4), "day_usd": round(d, 4), "hour_cap": self.h, "day_cap": self.d,
                "exhausted": h >= self.h or d >= self.d}
