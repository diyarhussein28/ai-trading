"""Deterministic rule-based agents: same contract as the LLM agents.

Used for `agents.backend: rules` (no API key), the offline demo, and tests. They encode the same
criteria the prompts describe, so they also serve as a transparent baseline to compare the LLM against.
"""
from __future__ import annotations


def _clamp(x: float) -> int:
    return max(0, min(100, round(x)))


def _vote(score: float, reason: str, flags: list[str] | None = None, threshold: int = 70, buy_ok: bool = True) -> dict:
    s = _clamp(score)
    return {"vote": "BUY" if (s >= threshold and buy_ok) else "PASS", "score": s, "reason": reason[:400],
            "red_flags": flags or []}


def _profile_links(ctx: dict) -> int:
    p = ctx.get("profile") or {}
    return int(bool(p.get("has_twitter"))) + int(bool(p.get("has_telegram"))) + int(bool(p.get("has_website")))


def detective(ctx: dict) -> dict:
    soc = ctx.get("social") or {}
    if not soc.get("available") or not soc.get("posts"):
        if ctx.get("social_policy") == "degrade":
            links = _profile_links(ctx)
            if links >= 2:
                return _vote(min(75, 60 + 5 * links), f"no X data; profile has {links} real links (degraded mode)")
            return _vote(30, f"no X data and only {links} profile link(s)", ["thin profile"])
        return _vote(0, f"social data unavailable: {soc.get('status', 'missing')}", ["no social data"], buy_ok=False)

    flags, s = [], 40.0
    authors = soc.get("distinct_authors", 0)
    aged = soc.get("aged_author_share", 0)
    dup = soc.get("duplicate_text_share", 0)
    s += 15 if authors >= 8 else 8 if authors >= 5 else -10
    s += 12 if aged >= 0.6 else (-20 if aged < 0.3 else 0)
    if dup > 0.3:
        s -= 25
        flags.append(f"copy-paste text {dup:.0%}")
    elif dup <= 0.1:
        s += 5
    if soc.get("growing"):
        s += 10
    if soc.get("posts_last_15m", 0) >= 5:
        s += 8
    if soc.get("total_likes", 0) >= 50:
        s += 5
    if aged < 0.3:
        flags.append("mostly new accounts")
    reason = (f"{authors} authors, {aged:.0%} aged, {dup:.0%} duplicate, "
              f"{soc.get('posts_last_15m', 0)} posts/15m, growing={soc.get('growing')}")
    return _vote(s, reason, flags, buy_ok=dup <= 0.3 and authors >= 5)


def sniper(ctx: dict) -> dict:
    soc = ctx.get("social") or {}
    age = (ctx.get("market") or {}).get("age_min") or 999
    if not soc.get("available") or not soc.get("posts"):
        if ctx.get("social_policy") == "degrade":
            p = ctx.get("profile") or {}
            if age <= 60 and p.get("has_twitter") and (p.get("has_website") or p.get("has_telegram")):
                return _vote(72, f"fresh launch ({age:.0f}m) with complete profile (degraded mode)")
            return _vote(30, "no X data and no fresh, complete profile")
        return _vote(0, f"social data unavailable: {soc.get('status', 'missing')}", ["no social data"], buy_ok=False)

    big = soc.get("big_accounts_last_60m") or []
    if not big:
        return _vote(35, "no credible large account or news in the last 60 min - not a catalyst")
    top = max(b.get("followers") or 0 for b in big)
    s = 65 + 8 * min(len(big), 3) + (10 if top >= 100_000 else 0) + (3 if age <= 60 else -5)
    return _vote(min(s, 95), f"{len(big)} large account(s) posted in 60m, top {top:,} followers; token {age:.0f}m old")


def professor(ctx: dict) -> dict:
    m = ctx.get("market") or {}
    saf = ctx.get("safety") or {}
    flags = list(ctx.get("minor_flags") or [])
    ratio = m.get("buys_m5", 0) / max(m.get("sells_m5", 0), 1)
    liq = m.get("liquidity_usd", 0) or 1
    vlr = m.get("vol_m5", 0) / liq
    chg = m.get("price_change_m5", 0)

    s = 40.0
    s += 15 if ratio >= 2 else 10 if ratio >= 1.5 else 5 if ratio >= 1.2 else -15
    s += 15 if vlr >= 1 else 10 if vlr >= 0.5 else 5 if vlr >= 0.25 else -10
    if 5 <= chg <= 60:
        s += 10
    elif 60 < chg <= 100:
        s += 3
    elif chg < 0:
        s -= 10
    if liq >= 25_000:
        s += 5
    trend = ctx.get("trend") or []
    if len(trend) >= 2 and trend[-1].get("vol_m5", 0) > trend[-2].get("vol_m5", 0):
        s += 5
    if (saf.get("holders") or 0) >= 300:
        s += 5
    s -= 8 * len(flags)

    col = ctx.get("colleagues") or {}
    both_buy = bool(col) and all(v.get("vote") == "BUY" for v in col.values())
    reason = (f"buys/sells {ratio:.2f}, vol5m/liq {vlr:.2f}, 5m {chg:+.0f}%, liq ${liq:,.0f}, "
              f"holders {saf.get('holders')}, {len(flags)} minor flag(s)")
    if col and not both_buy:
        reason += "; colleagues not unanimous"
    return _vote(s, reason, flags)


RULES = {"detective": detective, "sniper": sniper, "professor": professor}
