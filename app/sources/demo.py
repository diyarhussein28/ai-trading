"""Synthetic market for `python -m app.main demo`: exercises the whole pipeline offline, no keys, no network.

Each fake token follows a scripted regime (dud, pump, fade, rug, chop, unsafe) so every filter, safety
rule, vote path and exit reason gets hit. Numbers are made up - demo results say nothing about real edge.
"""
from __future__ import annotations

import asyncio
import math
import random
import string
import time

REGIMES = [("dud", 0.35), ("pump", 0.2), ("fade", 0.15), ("rug", 0.1), ("chop", 0.1), ("unsafe", 0.1)]


def _pick(rng: random.Random) -> str:
    x, acc = rng.random(), 0.0
    for name, w in REGIMES:
        acc += w
        if x <= acc:
            return name
    return "dud"


class DemoToken:
    def __init__(self, rng: random.Random, t0: float):
        self.rng = rng
        self.mint = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(40)) + "pump"
        self.symbol = "".join(rng.choice(string.ascii_uppercase) for _ in range(rng.randint(3, 6)))
        self.regime = _pick(rng)
        self.t0 = t0 - rng.uniform(2, 8) * 60  # pretend the pair was created a few minutes ago
        self.base_price = rng.uniform(2e-5, 5e-4)
        self.base_liq = rng.uniform(12_000, 60_000) if self.regime != "dud" else rng.uniform(1_000, 8_000)
        self.rug_after = rng.uniform(40, 120)
        self.noise = 0.0
        self.good_social = self.regime in ("pump", "chop") or rng.random() < 0.3

    def snapshot(self, now: float, sol_usd: float) -> dict:
        age_s = now - self.t0
        t = max(0.0, age_s - 300)  # regimes play out after the first ~5 minutes
        self.noise = 0.85 * self.noise + self.rng.gauss(0, 0.02)
        drift = {
            "pump": 0.55 * (1 - math.exp(-t / 90)),
            "fade": -0.35 * (1 - math.exp(-t / 120)),
            "rug": 0.1 * min(t / 60, 1),
            "chop": 0.12 * math.sin(t / 25),
            "dud": -0.05,
            "unsafe": 0.2 * (1 - math.exp(-t / 80)),
        }[self.regime]
        price = self.base_price * math.exp(drift + self.noise)
        liq = self.base_liq * (1 + drift / 2)
        if self.regime == "rug" and t > self.rug_after:
            liq *= 0.15
            price *= 0.3
        hot = self.regime in ("pump", "chop", "unsafe", "rug") and t < 240
        vol_m5 = liq * (self.rng.uniform(0.4, 1.6) if hot else self.rng.uniform(0.05, 0.3))
        buys = int(self.rng.uniform(80, 400) if hot else self.rng.uniform(10, 60))
        sells = int(buys / (self.rng.uniform(1.4, 2.6) if hot else self.rng.uniform(0.6, 1.3)))
        return {
            "mint": self.mint, "symbol": self.symbol, "name": self.symbol.title(), "ts": int(now),
            "dex": "pumpswap", "pair": self.mint[:20], "url": None,
            "price_usd": price, "price_native": price / sol_usd, "sol_usd": sol_usd,
            "liquidity_usd": liq, "vol_m5": vol_m5, "vol_h1": vol_m5 * 6,
            "buys_m5": buys, "sells_m5": max(sells, 1), "buys_h1": buys * 6, "sells_h1": sells * 6,
            "price_change_m5": (math.exp(drift + self.noise) - 1) * 100 * (0.6 if hot else 0.3),
            "price_change_h1": (math.exp(drift) - 1) * 100,
            "fdv": price * 1e9, "market_cap": price * 1e9, "age_min": age_s / 60,
            "socials": [{"type": "twitter", "url": "https://x.com/example"}] if self.good_social else [],
            "websites": [{"url": "https://example.com"}] if self.rng.random() < 0.6 else [],
            "boosts": 0,
        }

    def safety(self) -> dict:
        unsafe = self.regime == "unsafe"
        return {
            "source": "demo", "mint_authority_revoked": not unsafe, "freeze_authority_revoked": True,
            "top10_pct": 45.0 if unsafe else self.rng.uniform(8, 26), "dev_pct": self.rng.uniform(0, 3),
            "bundle_pct": self.rng.uniform(0, 10), "insider_networks": 0, "lp_locked_pct": 100.0,
            "lp_status": "burned_or_locked", "quote_liquidity_usd": self.base_liq / 2, "holders": self.rng.randint(120, 1500), "rug_score": 20.0,
            "rugged": False, "mutable_metadata": False, "transfer_fee_pct": 0.0, "risks": [], "launchpad": "pump_fun",
        }

    def posts(self, now: float) -> list[dict]:
        n = self.rng.randint(12, 25)
        out = []
        for i in range(n):
            organic = self.good_social and self.rng.random() < 0.85
            out.append({
                "author": f"user{self.rng.randint(1, 10_000 if organic else 6)}",
                "author_age_days": self.rng.uniform(60, 2000) if organic else self.rng.uniform(0, 5),
                "followers": int(self.rng.choice([150, 900, 4_000, 25_000, 140_000])) if organic else 20,
                "verified": False,
                "minutes_ago": self.rng.uniform(0, 14) if organic else self.rng.uniform(0, 60),
                "text": (f"${self.symbol} chart looks clean, community growing #{i}" if organic
                         else f"${self.symbol} 100x GEM BUY NOW"),
                "likes": self.rng.randint(5, 200) if organic else 0, "reposts": 0, "replies": 0,
            })
        return out


class DemoMarket:
    """Implements the DexScreener + SafetyClient + SocialClient + launch-stream surfaces."""

    def __init__(self, seed: int = 7, launches_per_minute: float = 20):
        self.rng = random.Random(seed)
        self.tokens: dict[str, DemoToken] = {}
        self.sol_usd = 150.0
        self.rate = launches_per_minute
        self.http_429 = 0
        self.errors = 0
        self.posts_fetched = 0
        self.last_message_at = time.time()
        self.connected = True
        self.reconnects = 0
        self.enabled = True

    # launch stream
    async def run_stream(self, on_event) -> None:
        while True:
            await asyncio.sleep(self.rng.expovariate(self.rate / 60))
            tok = DemoToken(self.rng, time.time())
            self.tokens[tok.mint] = tok
            self.last_message_at = time.time()
            await on_event({"mint": tok.mint, "symbol": tok.symbol, "name": tok.symbol, "creator": None,
                            "event": "migrate" if tok.regime != "dud" else "create"})

    def stale_seconds(self) -> float:
        return time.time() - self.last_message_at

    # DexScreener surface
    async def snapshots(self, mints: list[str]) -> dict[str, dict]:
        now = time.time()
        return {m: self.tokens[m].snapshot(now, self.sol_usd) for m in mints if m in self.tokens}

    async def snapshot(self, mint: str) -> dict | None:
        return (await self.snapshots([mint])).get(mint)

    async def latest_profiles(self) -> list[dict]:
        return []

    # Safety surface
    async def report(self, mint: str) -> dict | None:
        t = self.tokens.get(mint)
        return t.safety() if t else None

    # Social surface
    async def fetch(self, mint: str, symbol: str | None):
        t = self.tokens.get(mint)
        if not t:
            return None, "unknown token"
        posts = t.posts(time.time())
        self.posts_fetched += len(posts)
        return posts, "demo"

    async def aclose(self) -> None:
        return None
