"""3/3 consensus + Professor veto + composite Confidence Score + sizing (blueprint 10.2, 12.5)."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .sizing import composite_score, size_for


@dataclass
class Decision:
    decision_key: str
    unanimous: bool
    score: int
    size_sol: float
    votes: dict
    note: str


async def decide(team: dict, ctx: dict, cfg: dict, db) -> Decision:
    mint, symbol, version = ctx["mint"], ctx.get("symbol"), cfg["version"]
    key = f"{mint}:{int(time.time() * 1000)}"
    c = cfg["consensus"]

    det, snp = await asyncio.gather(team["detective"].vote(ctx), team["sniper"].vote(ctx))
    votes = {"detective": det, "sniper": snp}

    if c.get("short_circuit", True) and (det["vote"] != "BUY" or snp["vote"] != "BUY"):
        votes["professor"] = {"vote": "PASS", "score": 0, "red_flags": [],
                              "reason": "not consulted: Detective/Sniper not unanimous"}
    else:
        votes["professor"] = await team["professor"].vote({**ctx, "colleagues": {
            "detective": det, "sniper": snp}})

    for name, v in votes.items():
        await db.save_vote(version, mint, key, name, v)
        await db.add_blackboard(mint, symbol, name, f"vote {v['vote']} {v['score']}", v.get("reason", ""))

    unanimous = all(v["vote"] == "BUY" for v in votes.values())
    if c.get("professor_veto", True) and votes["professor"]["vote"] != "BUY":
        unanimous = False
    flags = ctx.get("minor_flags") or []
    score = composite_score(votes, c["weights"], penalties=len(flags), penalty_points=c.get("penalty_per_minor_flag", 10))
    size = size_for(score, cfg) if unanimous else 0.0

    if not unanimous:
        note = "no consensus: " + ", ".join(f"{n} {v['vote']}" for n, v in votes.items())
    elif size <= 0:
        note = f"consensus but confidence {score} < {cfg['sizing']['min_confidence_to_trade']}"
    else:
        note = f"consensus, confidence {score} -> {size:.4f} SOL"
    return Decision(key, unanimous, score, size, votes, note)
