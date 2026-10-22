"""Hard filter + safety gate (blueprint 12.3). Pure code: no LLM, no X calls."""
from __future__ import annotations


def market_filter(s: dict, cfg: dict) -> tuple[bool, list[str]]:
    f, r = cfg["filters"], []
    if s["liquidity_usd"] < f["min_liquidity_usd"]:
        r.append(f"low liquidity ${s['liquidity_usd']:,.0f}")
    if s["vol_m5"] < f["min_volume_m5_usd"]:
        r.append(f"low 5m volume ${s['vol_m5']:,.0f}")
    if s["buys_m5"] / max(s["sells_m5"], 1) < f["min_buy_sell_ratio_m5"]:
        r.append(f"buyers do not lead ({s['buys_m5']}/{s['sells_m5']})")
    age = s.get("age_min")
    if age is not None and not (f["min_age_minutes"] <= age <= f["max_age_minutes"]):
        r.append(f"age out of window ({age:.0f}m)")
    if s["price_change_m5"] > f["max_price_change_m5_pct"]:
        r.append(f"already parabolic (+{s['price_change_m5']:.0f}% 5m)")
    if s["price_change_m5"] < f.get("min_price_change_m5_pct", -100):
        r.append(f"dumping ({s['price_change_m5']:.0f}% 5m)")
    if s["price_usd"] <= 0:
        r.append("no price")
    return not r, r


def safety_gate(rep: dict | None, cfg: dict) -> tuple[bool, list[str]]:
    s, r = cfg["safety"], []
    if rep is None:
        return (False, ["BLOCK: safety data unavailable"]) if s["block_on_api_error"] else (True, [])
    if s.get("block_if_rugged_flag", True) and rep.get("rugged"):
        r.append("flagged as rugged")
    if s["require_mint_authority_revoked"] and not rep["mint_authority_revoked"]:
        r.append("mint authority active")
    if s["require_freeze_authority_revoked"] and not rep["freeze_authority_revoked"]:
        r.append("freeze authority active")
    if rep["top10_pct"] > s["max_top10_holders_pct"]:
        r.append(f"top10 concentrated ({rep['top10_pct']:.0f}%)")
    if rep["dev_pct"] > s["max_dev_holding_pct"]:
        r.append(f"dev holds too much ({rep['dev_pct']:.1f}%)")
    if (rep.get("bundle_pct") or 0) > s["max_bundle_pct"]:
        r.append(f"bundled launch ({rep['bundle_pct']:.0f}% insiders)")
    lp = rep.get("lp_locked_pct")
    if lp is not None and lp < s.get("min_lp_locked_pct", 0):
        r.append(f"LP not locked ({lp:.0f}%)")
    if (rep.get("holders") or 0) < s.get("min_holders", 0):
        r.append(f"too few holders ({rep.get('holders')})")
    if (rep.get("transfer_fee_pct") or 0) > 0:
        r.append("transfer fee (token-2022 tax)")
    q = rep.get("quote_liquidity_usd")
    if q is not None and q < s.get("min_quote_liquidity_usd", 0):
        r.append(f"pool holds only ${q:,.0f} of SOL")
    if s.get("block_on_rugcheck_danger", True):
        r += [f"rugcheck danger: {x.get('name')}" for x in rep.get("risks") or [] if x.get("level") == "danger"]
    return not r, r


def minor_flags(rep: dict | None, cfg: dict) -> list[str]:
    """Soft warnings: each one costs `penalty_per_minor_flag` confidence points (blueprint 10.2 step 3)."""
    if not rep:
        return []
    s, m, out = cfg["safety"], cfg["safety"].get("minor_flag_margin", 0.8), []
    if rep["top10_pct"] > s["max_top10_holders_pct"] * m:
        out.append(f"top10 near limit ({rep['top10_pct']:.0f}%)")
    if rep["dev_pct"] > s["max_dev_holding_pct"] * m:
        out.append(f"dev near limit ({rep['dev_pct']:.1f}%)")
    if (rep.get("bundle_pct") or 0) > s["max_bundle_pct"] * m:
        out.append("insider share near limit")
    if rep.get("lp_status") == "unknown":
        out.append("LP status unknown")
    if rep.get("mutable_metadata"):
        out.append("metadata mutable")
    if rep.get("insider_networks"):
        out.append(f"{rep['insider_networks']} insider network(s)")
    out += [f"rugcheck warn: {r.get('name')}" for r in rep.get("risks") or [] if r.get("level") == "warn"][:3]
    return out
