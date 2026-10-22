"""Budgeted, cached X data via the OFFICIAL X API v2 (blueprint 11.3).

Only called for tokens that already passed the market filter AND the safety gate.
Browser-session / cookie scraping (what the video did) is deliberately not implemented: it violates
X's terms, gets accounts banned, and a mid-test ban corrupts the 100-trade statistics.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from .budget import SpendGuard

log = logging.getLogger("social")
SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


def _parse_ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_search(payload: dict) -> list[dict]:
    users = {u["id"]: u for u in (payload.get("includes") or {}).get("users", [])}
    now = time.time()
    posts = []
    for t in payload.get("data") or []:
        u = users.get(t.get("author_id"), {})
        um = u.get("public_metrics") or {}
        tm = t.get("public_metrics") or {}
        created = _parse_ts(t.get("created_at"))
        acct_created = _parse_ts(u.get("created_at"))
        posts.append({
            "author": u.get("username"),
            "author_age_days": round((now - acct_created) / 86400, 1) if acct_created else None,
            "followers": um.get("followers_count"),
            "verified": bool(u.get("verified")),
            "minutes_ago": round((now - created) / 60, 1) if created else None,
            "text": (t.get("text") or "")[:240],
            "likes": tm.get("like_count", 0),
            "reposts": tm.get("retweet_count", 0),
            "replies": tm.get("reply_count", 0),
        })
    return posts


def summarize(posts: list[dict] | None, big_followers: int, aged_days: int) -> dict[str, Any]:
    """Deterministic social features that every agent (LLM or rules) sees."""
    if not posts:
        return {"available": posts is not None, "posts": 0}
    authors = {p["author"] for p in posts if p.get("author")}
    aged = [p for p in posts if (p.get("author_age_days") or 0) >= aged_days]
    texts = [" ".join((p.get("text") or "").lower().split()) for p in posts]
    dup = len(texts) - len(set(texts))
    recent15 = sum(1 for p in posts if (p.get("minutes_ago") or 1e9) <= 15)
    older = sum(1 for p in posts if 15 < (p.get("minutes_ago") or 1e9) <= 60)
    big = sorted(
        [p for p in posts if (p.get("followers") or 0) >= big_followers and (p.get("minutes_ago") or 1e9) <= 60],
        key=lambda p: -(p.get("followers") or 0))
    return {
        "available": True,
        "posts": len(posts),
        "distinct_authors": len(authors),
        "aged_author_share": round(len(aged) / len(posts), 2),
        "duplicate_text_share": round(dup / len(posts), 2),
        "posts_last_15m": recent15,
        "posts_15_60m": older,
        "growing": recent15 > older / 3 if older else recent15 >= 3,
        "total_likes": sum(p.get("likes") or 0 for p in posts),
        "big_accounts_last_60m": [{"author": p["author"], "followers": p["followers"],
                                   "minutes_ago": p["minutes_ago"], "text": p["text"][:160]} for p in big[:5]],
    }


class SocialClient:
    def __init__(self, db, cfg: dict, bearer_token: str | None, client: httpx.AsyncClient | None = None):
        self.db = db
        self.cfg = cfg["social"]
        self.token = bearer_token
        self.c = client or httpx.AsyncClient(timeout=15)
        self.guard = SpendGuard(db, self.cfg["hourly_budget_usd"], self.cfg["daily_budget_usd"])
        self.posts_fetched = 0

    @property
    def enabled(self) -> bool:
        return bool(self.cfg["enabled"] and self.token)

    async def fetch(self, mint: str, symbol: str | None) -> tuple[list[dict] | None, str]:
        """Returns (posts, status). posts=None means 'no data' (disabled, budget, error)."""
        if not self.enabled:
            return None, "social disabled (no X_BEARER_TOKEN)"
        cached = await self.db.social_get(mint, self.cfg["cache_minutes"] * 60)
        if cached is not None:
            return cached, "cache"
        n = self.cfg["max_posts_per_token"]
        est = n * self.cfg["est_usd_per_post"]
        if not await self.guard.allow("x_api", est):
            return None, "social budget exhausted"
        terms = [f'"{mint}"']
        if symbol and symbol.isascii() and 2 <= len(symbol) <= 12 and symbol.replace("_", "").isalnum():
            terms.append(f"${symbol}" if not symbol[0].isdigit() else f'"{symbol}"')
        query = f"({' OR '.join(terms)}) -is:retweet"
        params = {
            "query": query, "max_results": n,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id", "user.fields": "created_at,public_metrics,verified",
        }
        try:
            r = await self.c.get(SEARCH_URL, params=params, headers={"Authorization": f"Bearer {self.token}"})
            if r.status_code == 429:
                return None, "X rate limited (429)"
            r.raise_for_status()
            posts = parse_search(r.json())
        except Exception as e:
            log.warning("X search failed for %s: %s", mint, e)
            return None, f"X error: {type(e).__name__}"
        usd = len(posts) * self.cfg["est_usd_per_post"]
        await self.guard.record("x_api", len(posts), usd, note=mint)
        await self.db.social_put(mint, posts, len(posts))
        self.posts_fetched += len(posts)
        return posts, "fresh"

    async def aclose(self) -> None:
        await self.c.aclose()
