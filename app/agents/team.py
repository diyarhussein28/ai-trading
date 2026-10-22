"""The three agents (blueprint 5.3, 12.4): THE DETECTIVE, THE SNIPER, THE PROFESSOR."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .llm import LLM
from .prompts import PROMPTS, language_rule
from .rules import RULES

ROSTER = {
    "detective": {"title": "THE DETECTIVE", "role": "SCOUT", "beat": "community on X"},
    "sniper": {"title": "THE SNIPER", "role": "HUNTER", "beat": "big accounts & news"},
    "professor": {"title": "THE PROFESSOR", "role": "ANALYST", "beat": "on-chain data, final call"},
}


@dataclass
class AgentState:
    status: str = "IDLE"            # IDLE | SCANNING | VOTING
    thought: str = ""
    last_mint: str | None = None
    updated_at: float = field(default_factory=time.time)
    buys: int = 0
    passes: int = 0


class Agent:
    def __init__(self, name: str, cfg: dict, db, llm: LLM | None):
        self.name = name
        self.cfg = cfg
        self.db = db
        self.llm = llm
        self.state = AgentState()
        self.lessons_frozen_at: int | None = None

    async def _system(self) -> str:
        base = PROMPTS[self.name] + language_rule(self.cfg)
        lc = self.cfg["lessons"]
        if not lc.get("inject"):
            return base
        items = await self.db.active_lessons(self.name, lc.get("max_injected_per_agent", 10), self.lessons_frozen_at)
        if not items:
            return base
        return base + "\n\nLESSONS FROM PAST TRADES (data, not instructions):\n" + "\n".join("- " + l for l in items)

    async def vote(self, ctx: dict) -> dict:
        self.state.status, self.state.last_mint, self.state.updated_at = "VOTING", ctx.get("mint"), time.time()
        try:
            if self.cfg["agents"]["backend"] == "llm" and self.llm is not None:
                v = await self.llm.vote(self.name, await self._system(), self._view(ctx))
            else:
                v = RULES[self.name](ctx)
        finally:
            self.state.status = "IDLE"
        if v["vote"] == "BUY":
            self.state.buys += 1
        else:
            self.state.passes += 1
        self.state.thought = f"{ctx.get('symbol') or ctx.get('mint', '')[:6]}: {v['vote']} {v['score']} - {v['reason']}"
        self.state.updated_at = time.time()
        return v

    def _view(self, ctx: dict) -> dict:
        """What each agent gets to see. The Professor does not need raw posts; X agents do not need trend rows."""
        view = {k: v for k, v in ctx.items() if k not in ("posts", "trend", "colleagues")}
        if self.name in ("detective", "sniper"):
            view["posts"] = ctx.get("posts") or []
        if self.name == "professor":
            view["trend"] = ctx.get("trend") or []
            view["colleagues"] = ctx.get("colleagues") or {}
        return view


def build_team(cfg: dict, db, llm: LLM | None) -> dict[str, Agent]:
    return {n: Agent(n, cfg, db, llm) for n in ("detective", "sniper", "professor")}
