"""Claude calls for votes (fast model) and post-mortems (strong model), with structured JSON output and cost logging."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import anthropic

log = logging.getLogger("llm")

VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["BUY", "PASS"]},
        "score": {"type": "integer"},
        "reason": {"type": "string"},
        "red_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["vote", "score", "reason", "red_flags"],
    "additionalProperties": False,
}

LESSON_SCHEMA = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": ["detective", "sniper", "professor"]},
                    "lesson": {"type": "string"},
                },
                "required": ["agent", "lesson"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["lessons"],
    "additionalProperties": False,
}

FALLBACK_VOTE = {"vote": "PASS", "score": 0, "red_flags": []}


def normalize_vote(o: Any) -> dict:
    """Never trust model output blindly: anything malformed becomes a PASS."""
    try:
        vote = str(o["vote"]).upper()
        score = int(o["score"])
        if vote not in ("BUY", "PASS"):
            raise ValueError(vote)
        return {
            "vote": vote,
            "score": max(0, min(100, score)),
            "reason": str(o.get("reason", ""))[:400],
            "red_flags": [str(x)[:80] for x in (o.get("red_flags") or [])][:8],
        }
    except Exception:
        return {**FALLBACK_VOTE, "reason": "invalid output"}


class LLM:
    def __init__(self, cfg: dict, db, client: anthropic.AsyncAnthropic | None = None):
        a = cfg["agents"]
        self.cfg = cfg
        self.db = db
        self.vote_model = os.environ.get(a["vote_model_env"], "claude-haiku-5-5")
        self.review_model = os.environ.get(a["review_model_env"], "claude-opus-5-5")
        self.effort = a.get("vote_effort", "low")
        self.client = client or anthropic.AsyncAnthropic(timeout=a.get("timeout_seconds", 45), max_retries=2)
        self.prices = cfg.get("llm_pricing_usd_per_mtok", {})
        self.calls = 0
        self.failures = 0

    async def _record(self, model: str, usage, note: str) -> None:
        if usage is None:
            return
        p_in, p_out = self.prices.get(model, (0.0, 0.0))
        tin = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        tout = usage.output_tokens or 0
        usd = (tin * p_in + tout * p_out) / 1e6
        await self.db.insert_spend("llm", tin + tout, usd, note=f"{model} {note}")

    async def vote(self, agent: str, system: str, ctx: dict) -> dict:
        self.calls += 1
        try:
            resp = await self.client.messages.create(
                model=self.vote_model,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": json.dumps(ctx, ensure_ascii=False, default=str)}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": VOTE_SCHEMA}},
            )
        except anthropic.RateLimitError as e:
            self.failures += 1
            log.warning("%s vote rate-limited: %s", agent, e)
            return {**FALLBACK_VOTE, "reason": "LLM rate limited"}
        except anthropic.APIStatusError as e:
            self.failures += 1
            log.warning("%s vote API error %s: %s", agent, e.status_code, e)
            return {**FALLBACK_VOTE, "reason": f"LLM error {e.status_code}"}
        except anthropic.APIConnectionError as e:
            self.failures += 1
            log.warning("%s vote connection error: %s", agent, e)
            return {**FALLBACK_VOTE, "reason": "LLM unreachable"}
        await self._record(self.vote_model, resp.usage, f"vote:{agent}")
        if resp.stop_reason == "refusal":
            return {**FALLBACK_VOTE, "reason": "model declined"}
        if resp.stop_reason == "max_tokens":
            return {**FALLBACK_VOTE, "reason": "output truncated"}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return normalize_vote(json.loads(text))
        except ValueError:
            return {**FALLBACK_VOTE, "reason": "invalid output"}

    async def post_mortem(self, system: str, trade: dict) -> list[dict]:
        try:
            resp = await self.client.beta.messages.create(
                model=self.review_model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": json.dumps(trade, ensure_ascii=False, default=str)}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": LESSON_SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as e:
            log.warning("post-mortem failed: %s", e)
            return []
        await self._record(self.review_model, resp.usage, "post_mortem")
        if resp.stop_reason in ("refusal", "max_tokens"):
            return []
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            items = json.loads(text).get("lessons", [])
        except ValueError:
            return []
        return [{"agent": i["agent"], "lesson": str(i["lesson"])[:600]} for i in items
                if i.get("agent") in ("detective", "sniper", "professor") and i.get("lesson")]
