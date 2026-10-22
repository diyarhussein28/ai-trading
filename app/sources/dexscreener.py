"""DexScreener market data (blueprint 12.2) - batched, rate-limited, 429-aware."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Iterable

import httpx

log = logging.getLogger("dexscreener")


class RateLimiter:
    """Simple spacing limiter: at most `per_minute` calls, evenly spaced."""

    def __init__(self, per_minute: int):
        self.interval = 60.0 / per_minute
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            t = time.monotonic()
            if t < self._next:
                await asyncio.sleep(self._next - t)
            self._next = max(t, self._next) + self.interval


def _num(x, default=0.0) -> float:
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def parse_pair(mint: str, p: dict) -> dict[str, Any]:
    m5 = (p.get("txns") or {}).get("m5") or {}
    h1 = (p.get("txns") or {}).get("h1") or {}
    created = p.get("pairCreatedAt") or 0
    price_usd = _num(p.get("priceUsd"))
    price_native = _num(p.get("priceNative"))
    info = p.get("info") or {}
    return {
        "mint": mint,
        "symbol": (p.get("baseToken") or {}).get("symbol"),
        "name": (p.get("baseToken") or {}).get("name"),
        "ts": int(time.time()),
        "dex": p.get("dexId"),
        "pair": p.get("pairAddress"),
        "url": p.get("url"),
        "price_usd": price_usd,
        "price_native": price_native,
        "sol_usd": (price_usd / price_native) if price_native > 0 else None,
        "liquidity_usd": _num((p.get("liquidity") or {}).get("usd")),
        "vol_m5": _num((p.get("volume") or {}).get("m5")),
        "vol_h1": _num((p.get("volume") or {}).get("h1")),
        "buys_m5": int(m5.get("buys") or 0),
        "sells_m5": int(m5.get("sells") or 0),
        "buys_h1": int(h1.get("buys") or 0),
        "sells_h1": int(h1.get("sells") or 0),
        "price_change_m5": _num((p.get("priceChange") or {}).get("m5")),
        "price_change_h1": _num((p.get("priceChange") or {}).get("h1")),
        "fdv": _num(p.get("fdv")),
        "market_cap": _num(p.get("marketCap")),
        "age_min": (time.time() * 1000 - created) / 60000 if created else None,
        "socials": info.get("socials") or [],
        "websites": info.get("websites") or [],
        "boosts": (p.get("boosts") or {}).get("active", 0),
    }


def best_pairs(mints: Iterable[str], pairs: list[dict]) -> dict[str, dict]:
    """Pick the deepest Solana pair per base token."""
    wanted = set(mints)
    best: dict[str, dict] = {}
    for p in pairs or []:
        if p.get("chainId") != "solana":
            continue
        mint = (p.get("baseToken") or {}).get("address")
        if mint not in wanted:
            continue
        liq = _num((p.get("liquidity") or {}).get("usd"))
        if mint not in best or liq > _num((best[mint].get("liquidity") or {}).get("usd")):
            best[mint] = p
    return {m: parse_pair(m, p) for m, p in best.items()}


class DexScreener:
    BASE = "https://api.dexscreener.com"

    def __init__(self, client: httpx.AsyncClient | None = None, pairs_per_min: int = 280, profiles_per_min: int = 55):
        self.c = client or httpx.AsyncClient(timeout=10, headers={"Accept": "application/json"})
        self.pairs_rl = RateLimiter(pairs_per_min)        # documented limit 300/min
        self.profiles_rl = RateLimiter(profiles_per_min)  # documented limit 60/min
        self.http_429 = 0
        self.sol_usd: float | None = None

    async def _get(self, path: str, limiter: RateLimiter):
        for i in range(5):
            await limiter.wait()
            try:
                r = await self.c.get(self.BASE + path)
            except httpx.HTTPError as e:
                log.warning("dexscreener %s: %s", path[:60], e)
                await asyncio.sleep(2 ** i)
                continue
            if r.status_code == 429:
                self.http_429 += 1
                await asyncio.sleep(2 ** i)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("DexScreener rate-limited")

    async def snapshots(self, mints: list[str]) -> dict[str, dict]:
        """Batch snapshot (<=30 mints per call). Mints with no Solana pair are absent from the result."""
        out: dict[str, dict] = {}
        for i in range(0, len(mints), 30):
            chunk = mints[i:i + 30]
            data = await self._get("/tokens/v1/solana/" + ",".join(chunk), self.pairs_rl)
            pairs = data if isinstance(data, list) else (data or {}).get("pairs") or []
            out.update(best_pairs(chunk, pairs))
        for s in out.values():
            if s.get("sol_usd"):
                self.sol_usd = s["sol_usd"]
        return out

    async def snapshot(self, mint: str) -> dict | None:
        return (await self.snapshots([mint])).get(mint)

    async def latest_profiles(self) -> list[dict]:
        out = []
        for path in ("/token-profiles/latest/v1", "/token-boosts/latest/v1"):
            try:
                data = await self._get(path, self.profiles_rl)
            except Exception as e:
                log.warning("profiles %s failed: %s", path, e)
                continue
            for d in data if isinstance(data, list) else []:
                if d.get("chainId") == "solana" and d.get("tokenAddress"):
                    out.append({"mint": d["tokenAddress"], "source": "boost" if "boost" in path else "profile",
                                "links": d.get("links") or []})
        return out

    async def aclose(self) -> None:
        await self.c.aclose()
