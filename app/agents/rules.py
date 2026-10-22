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
                return _vote(min(75, 60 + 5 * links), f"ما فيه بيانات X؛ صفحة العملة فيها {links} روابط حقيقية (وضع مخفّف)")
            return _vote(30, f"ما فيه بيانات X، وصفحة العملة فيها {links} رابط بس", ["صفحة ضعيفة"])
        return _vote(0, f"بيانات X غير متوفرة: {soc.get('status', 'missing')}", ["ما فيه بيانات اجتماعية"], buy_ok=False)

    flags, s = [], 40.0
    authors = soc.get("distinct_authors", 0)
    aged = soc.get("aged_author_share", 0)
    dup = soc.get("duplicate_text_share", 0)
    s += 15 if authors >= 8 else 8 if authors >= 5 else -10
    s += 12 if aged >= 0.6 else (-20 if aged < 0.3 else 0)
    if dup > 0.3:
        s -= 25
        flags.append(f"نصوص منسوخة {dup:.0%}")
    elif dup <= 0.1:
        s += 5
    if soc.get("growing"):
        s += 10
    if soc.get("posts_last_15m", 0) >= 5:
        s += 8
    if soc.get("total_likes", 0) >= 50:
        s += 5
    if aged < 0.3:
        flags.append("أغلب الحسابات جديدة")
    reason = (f"{authors} كاتب، {aged:.0%} حسابات قديمة، {dup:.0%} نصوص مكررة، "
              f"{soc.get('posts_last_15m', 0)} منشور آخر 15 دقيقة، {'النشاط يزيد' if soc.get('growing') else 'النشاط ما يزيد'}")
    return _vote(s, reason, flags, buy_ok=dup <= 0.3 and authors >= 5)


def sniper(ctx: dict) -> dict:
    soc = ctx.get("social") or {}
    age = (ctx.get("market") or {}).get("age_min") or 999
    if not soc.get("available") or not soc.get("posts"):
        if ctx.get("social_policy") == "degrade":
            p = ctx.get("profile") or {}
            if age <= 60 and p.get("has_twitter") and (p.get("has_website") or p.get("has_telegram")):
                return _vote(72, f"إطلاق جديد ({age:.0f} دقيقة) وصفحته مكتملة (وضع مخفّف)")
            return _vote(30, "ما فيه بيانات X ولا صفحة جديدة مكتملة")
        return _vote(0, f"بيانات X غير متوفرة: {soc.get('status', 'missing')}", ["ما فيه بيانات اجتماعية"], buy_ok=False)

    big = soc.get("big_accounts_last_60m") or []
    if not big:
        return _vote(35, "ما فيه حساب كبير موثوق ولا خبر آخر 60 دقيقة، يعني ما فيه محفّز")
    top = max(b.get("followers") or 0 for b in big)
    s = 65 + 8 * min(len(big), 3) + (10 if top >= 100_000 else 0) + (3 if age <= 60 else -5)
    return _vote(min(s, 95), f"{len(big)} حساب كبير نشر آخر 60 دقيقة، أكبرهم {top:,} متابع؛ عمر العملة {age:.0f} دقيقة")


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
    reason = (f"شراء/بيع {ratio:.2f}، حجم 5 دقائق/السيولة {vlr:.2f}، تغيّر 5 دقائق {chg:+.0f}%، السيولة ${liq:,.0f}، "
              f"الحاملين {saf.get('holders')}، تحذيرات بسيطة {len(flags)}")
    if col and not both_buy:
        reason += "؛ الزملاء ما اتفقوا"
    return _vote(s, reason, flags)


RULES = {"detective": detective, "sniper": sniper, "professor": professor}
