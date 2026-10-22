"""Safety data (blueprint 7.2, 12.3): RugCheck report + optional on-chain authority cross-check.

Any failure returns None, and the safety gate turns None into BLOCK.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .dexscreener import RateLimiter

log = logging.getLogger("safety")

POOL_ACCOUNT_TYPES = {"AMM", "LOCKER", "BURN", "EXCHANGE"}


def parse_rugcheck(d: dict) -> dict:
    """Normalise a RugCheck /v1/tokens/{mint}/report payload."""
    token = d.get("token") or {}
    supply = float(token.get("supply") or 0)
    known = d.get("knownAccounts") or {}
    pool_accounts = {a for a, info in known.items() if (info or {}).get("type") in POOL_ACCOUNT_TYPES}
    markets = d.get("markets") or []
    for m in markets:
        for k in ("pubkey", "liquidityA", "liquidityB", "liquidityAAccount", "liquidityBAccount"):
            if isinstance(m.get(k), str):
                pool_accounts.add(m[k])

    holders = d.get("topHolders") or []
    real = [h for h in holders if h.get("address") not in pool_accounts and h.get("owner") not in pool_accounts]
    top10_pct = sum(float(h.get("pct") or 0) for h in real[:10])
    bundle_pct = sum(float(h.get("pct") or 0) for h in real if h.get("insider"))

    creator = d.get("creator")
    creator_balance = float(d.get("creatorBalance") or 0)
    dev_pct = (creator_balance / supply * 100) if supply > 0 else 0.0
    # creatorBalance can lag; also count any top holder owned by the creator
    dev_pct = max(dev_pct, sum(float(h.get("pct") or 0) for h in real if creator and h.get("owner") == creator))

    lp_locked = [float((m.get("lp") or {}).get("lpLockedPct") or 0) for m in markets if m.get("lp")]
    # Real SOL-side depth. DexScreener's liquidity counts the token side at market price, which stays
    # high after a dev dumps into the pool; the quote side is what you can actually sell into.
    quote_usd = [float((m.get("lp") or {}).get("quoteUSD") or 0) for m in markets if m.get("lp")]
    lp_locked_pct = max(lp_locked) if lp_locked else None
    if lp_locked_pct is None:
        lp_status = "unknown"
    elif lp_locked_pct >= 99:
        lp_status = "burned_or_locked"
    elif lp_locked_pct >= 50:
        lp_status = "partly_locked"
    else:
        lp_status = "unlocked"

    risks = [{"name": r.get("name"), "level": r.get("level"), "value": r.get("value")} for r in d.get("risks") or []]
    mint_auth = d.get("mintAuthority", token.get("mintAuthority"))
    freeze_auth = d.get("freezeAuthority", token.get("freezeAuthority"))
    return {
        "source": "rugcheck",
        "mint_authority_revoked": mint_auth in (None, ""),
        "freeze_authority_revoked": freeze_auth in (None, ""),
        "top10_pct": round(top10_pct, 2),
        "dev_pct": round(dev_pct, 2),
        "bundle_pct": round(bundle_pct, 2),
        "insider_networks": len(d.get("insiderNetworks") or []),
        "lp_locked_pct": lp_locked_pct,
        "lp_status": lp_status,
        "holders": int(d.get("totalHolders") or 0),
        "quote_liquidity_usd": round(max(quote_usd), 2) if quote_usd else None,
        "total_market_liquidity_usd": float(d.get("totalMarketLiquidity") or 0),
        "rug_score": float(d.get("score_normalised") or 0),
        "rugged": bool(d.get("rugged")),
        "mutable_metadata": bool((d.get("tokenMeta") or {}).get("mutable")),
        "transfer_fee_pct": float((d.get("transferFee") or {}).get("pct") or 0),
        "risks": risks,
        "launchpad": (d.get("launchpad") or {}).get("platform"),
    }


class SafetyClient:
    BASE = "https://api.rugcheck.xyz/v1"

    def __init__(self, rpc_url: str | None = None, cache_seconds: int = 300,
                 client: httpx.AsyncClient | None = None):
        self.c = client or httpx.AsyncClient(timeout=15, headers={"Accept": "application/json"})
        self.rpc_url = rpc_url
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[float, dict]] = {}
        self.rl = RateLimiter(50)
        self.errors = 0

    async def report(self, mint: str) -> dict | None:
        hit = self._cache.get(mint)
        if hit and time.time() - hit[0] < self.cache_seconds:
            return hit[1]
        try:
            rep = await self._rugcheck(mint)
            if self.rpc_url:
                await self._cross_check_authorities(mint, rep)
        except Exception as e:
            self.errors += 1
            log.warning("safety report failed for %s: %s", mint, e)
            return None
        self._cache[mint] = (time.time(), rep)
        if len(self._cache) > 5000:
            for k in list(self._cache)[:1000]:
                self._cache.pop(k, None)
        return rep

    async def _rugcheck(self, mint: str) -> dict:
        for i in range(4):
            await self.rl.wait()
            r = await self.c.get(f"{self.BASE}/tokens/{mint}/report")
            if r.status_code == 429 or r.status_code >= 500:
                await asyncio.sleep(2 ** i)
                continue
            r.raise_for_status()
            return parse_rugcheck(r.json())
        raise RuntimeError(f"rugcheck unavailable for {mint}")

    async def _cross_check_authorities(self, mint: str, rep: dict) -> None:
        """Authorities straight from chain: if the RPC disagrees with RugCheck, trust the chain."""
        body = {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                "params": [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}]}
        r = await self.c.post(self.rpc_url, json=body)
        r.raise_for_status()
        info = (((r.json().get("result") or {}).get("value") or {}).get("data") or {}).get("parsed", {}).get("info", {})
        if not info:
            raise RuntimeError("mint account not found on chain")
        rep["mint_authority_revoked"] = info.get("mintAuthority") in (None, "")
        rep["freeze_authority_revoked"] = info.get("freezeAuthority") in (None, "")
        rep["source"] = "rugcheck+rpc"

    async def aclose(self) -> None:
        await self.c.aclose()
