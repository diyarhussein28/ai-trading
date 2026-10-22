"""Integration tests: DB, consensus, risk, full engine path (rules agents), LLM client guard, web."""
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agents.llm import LLM
from app.agents.team import build_team
from app.alerts import Alerter
from app.consensus import decide
from app.engine import Engine
from app.risk import RiskManager
from app.web import create_app

from .conftest import safety_rep, snap


class FakeDex:
    def __init__(self):
        self.snaps = {}
        self.sol_usd = 150.0
        self.http_429 = 0

    async def snapshots(self, mints):
        return {m: dict(self.snaps[m]) for m in mints if m in self.snaps}

    async def snapshot(self, mint):
        return (await self.snapshots([mint])).get(mint)

    async def latest_profiles(self):
        return []


class FakeSafety:
    def __init__(self, rep):
        self.rep = rep

    async def report(self, mint):
        return self.rep


class NoSocial:
    enabled = False


class FakeStream:
    connected = True

    def stale_seconds(self):
        return 1.0


def make_engine(cfg, db, rep=None):
    dex = FakeDex()
    return Engine(cfg, db, dex, FakeSafety(rep if rep is not None else safety_rep()), NoSocial(), FakeStream(),
                  None, Alerter()), dex


# ---------------------------------------------------------------- DB invariants
async def test_one_open_position_per_token(db):
    vals = dict(mint="M", symbol="S", version="V7", decision_id=1, confidence=80, size_sol=0.02,
                opened_at=int(time.time()), entry_price=1.0, entry_mid_price=1.0, entry_liq=1.0)
    assert await db.insert_position(**vals) is not None
    assert await db.insert_position(**vals) is None  # duplicate bet blocked by the partial unique index
    assert await db.open_count() == 1


async def test_meta_and_spend(db):
    await db.meta_set("k", {"a": 1})
    await db.meta_set("k", {"a": 2})
    assert await db.meta_get("k") == {"a": 2}
    await db.insert_spend("x_api", 25, 0.125)
    assert await db.spend_since("x_api", 0) == pytest.approx(0.125)


# ---------------------------------------------------------------- consensus
class StubAgent:
    def __init__(self, vote, score):
        self.v = {"vote": vote, "score": score, "reason": "stub", "red_flags": []}
        self.calls = 0

    async def vote(self, ctx):
        self.calls += 1
        return self.v


async def test_consensus_unanimous_sizes_trade(cfg, db):
    team = {"detective": StubAgent("BUY", 80), "sniper": StubAgent("BUY", 85), "professor": StubAgent("BUY", 90)}
    d = await decide(team, {"mint": "M", "symbol": "S", "minor_flags": []}, cfg, db)
    assert d.unanimous and d.score == round(90 * .45 + 85 * .3 + 80 * .25) and d.size_sol > 0
    assert len(await db.votes_for(d.decision_key)) == 3


async def test_professor_veto_and_short_circuit(cfg, db):
    team = {"detective": StubAgent("BUY", 90), "sniper": StubAgent("BUY", 90), "professor": StubAgent("PASS", 40)}
    d = await decide(team, {"mint": "M", "minor_flags": []}, cfg, db)
    assert not d.unanimous and d.size_sol == 0
    team = {"detective": StubAgent("PASS", 10), "sniper": StubAgent("BUY", 90), "professor": StubAgent("BUY", 99)}
    d = await decide(team, {"mint": "M", "minor_flags": []}, cfg, db)
    assert team["professor"].calls == 0 and not d.unanimous  # Professor not consulted -> no LLM cost


async def test_low_confidence_consensus_does_not_trade(cfg, db):
    team = {"detective": StubAgent("BUY", 72), "sniper": StubAgent("BUY", 72), "professor": StubAgent("BUY", 72)}
    d = await decide(team, {"mint": "M", "minor_flags": ["a"]}, cfg, db)  # 72 - 10 = 62 < 70
    assert d.unanimous and d.score == 62 and d.size_sol == 0


# ---------------------------------------------------------------- risk
async def _closed(db, mint, ret, closed_at=None):
    p = await db.insert_position(mint=mint, symbol=mint, version="V7", decision_id=0, confidence=80, size_sol=0.02,
                                 opened_at=int(time.time()) - 60, entry_price=1.0, entry_mid_price=1.0, entry_liq=1.0)
    await db.close_position(p["id"], 1 + ret / 100, ret, 0.02 * ret / 100, 0.001, "SL", 0.0,
                            closed_at or int(time.time()))


async def test_risk_cooldown_and_kill_switch(cfg, db):
    rm = RiskManager(cfg, db)
    assert (await rm.can_open("A"))[0]
    await _closed(db, "A", -25)
    ok, why = await rm.can_open("A")
    assert not ok and "cooldown" in why
    await _closed(db, "B", -30)
    await _closed(db, "C", -21)
    ok, why = await rm.can_open("D")
    assert not ok and "kill switch" in why


async def test_risk_daily_loss(cfg, db):
    cfg["risk"]["kill_switch_consecutive_losses"] = 0
    for m in ("A", "B", "C", "D"):
        await _closed(db, m, -80)  # 4 x -0.016 SOL = -0.064 <= -0.06
    ok, why = await RiskManager(cfg, db).can_open("E")
    assert not ok and "daily loss" in why


# ---------------------------------------------------------------- full engine path (rules agents, degraded social)
async def test_engine_evaluate_open_monitor_close(rules_cfg, db):
    eng, dex = make_engine(rules_cfg, db)
    s = snap(mint="GOOD", symbol="GOOD", vol_m5=40_000, buys_m5=500, sells_m5=200, age_min=20)
    dex.snaps["GOOD"] = s
    await eng.evaluate(s)
    open_pos = await db.open_positions()
    assert len(open_pos) == 1, await db.recent_candidates()
    p = open_pos[0]
    assert p["confidence"] >= 70 and p["size_sol"] > 0 and p["entry_price"] > s["price_usd"]

    dex.snaps["GOOD"] = snap(mint="GOOD", symbol="GOOD", price_usd=s["price_usd"] * 1.6)
    await eng.monitor_once()
    closed = await db.closed_positions()
    assert len(closed) == 1 and closed[0]["exit_reason"] == "TP" and closed[0]["pnl_sol"] > 0

    state = await eng.state()
    json.dumps(state)  # dashboard payload must be JSON-serialisable
    assert state["test"]["progress"] == 1 and state["agents"][0]["thought"]


async def test_engine_safety_block_spends_nothing(rules_cfg, db):
    eng, dex = make_engine(rules_cfg, db, rep=safety_rep(freeze_authority_revoked=False))
    s = snap(mint="BAD")
    dex.snaps["BAD"] = s
    await eng.evaluate(s)
    assert await db.open_count() == 0
    assert await db.decision_stats(0) == {"evaluated": 0, "consensus": 0, "taken": 0}  # agents never asked
    cands = await db.recent_candidates()
    assert cands[0]["stage"] == "safety" and "freeze" in cands[0]["reasons"][0]


async def test_engine_pass_policy_without_social_never_trades(cfg, db):
    cfg["agents"]["backend"] = "rules"  # social.on_missing stays 'pass' (blueprint default)
    eng, dex = make_engine(cfg, db)
    s = snap(mint="NOX")
    dex.snaps["NOX"] = s
    await eng.evaluate(s)
    assert await db.open_count() == 0


async def test_engine_skips_if_price_ran_away(rules_cfg, db):
    eng, dex = make_engine(rules_cfg, db)
    s = snap(mint="RUN", vol_m5=40_000, buys_m5=500, sells_m5=200)
    dex.snaps["RUN"] = snap(mint="RUN", price_usd=s["price_usd"] * 1.3, vol_m5=40_000, buys_m5=500, sells_m5=200)
    await eng.evaluate(s)
    assert await db.open_count() == 0


async def test_checkpoint_report_every_10_trades(rules_cfg, db):
    eng, _ = make_engine(rules_cfg, db)
    rules_cfg["risk"]["kill_switch_consecutive_losses"] = 0
    for i in range(10):
        p = await db.insert_position(mint=f"T{i}", symbol=f"T{i}", version=rules_cfg["version"], decision_id=0,
                                     confidence=80, size_sol=0.02, opened_at=int(time.time()) - 300,
                                     entry_price=1.0, entry_mid_price=1.0, entry_liq=1.0)
        await db.close_position(p["id"], 1.4, 40.0, 0.008, 0.001, "TP", 40.0, int(time.time()))
    await eng.checkpoint()
    reps = await db.recent_reports()
    assert len(reps) == 1 and reps[0]["trades"] == 10 and reps[0]["kind"] == "checkpoint"


async def test_config_drift_detected(rules_cfg, db):
    await db.meta_set(f"config_hash:{rules_cfg['version']}", "different")
    eng, _ = make_engine(rules_cfg, db)
    eng.demo = True
    eng.stream.run_stream = lambda cb: _never()
    await eng.start()
    try:
        assert eng.config_drift and "تغيّرت في نص الاختبار" in eng.config_drift
    finally:
        await eng.stop()


async def _never():
    import asyncio
    await asyncio.Event().wait()


# ---------------------------------------------------------------- LLM client guard (no network)
class FakeMessages:
    def __init__(self, text, stop="end_turn"):
        self.text, self.stop = text, stop
        self.kwargs = None

    async def create(self, **kw):
        self.kwargs = kw
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0))


async def test_llm_vote_structured_output_and_cost(cfg, db):
    msgs = FakeMessages(json.dumps({"vote": "BUY", "score": 83, "reason": "momentum", "red_flags": []}))
    llm = LLM(cfg, db, client=SimpleNamespace(messages=msgs))
    v = await llm.vote("professor", "sys", {"mint": "M"})
    assert v == {"vote": "BUY", "score": 83, "reason": "momentum", "red_flags": []}
    assert msgs.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in msgs.kwargs
    assert await db.spend_since("llm", 0) > 0


async def test_llm_refusal_and_garbage_become_pass(cfg, db):
    llm = LLM(cfg, db, client=SimpleNamespace(messages=FakeMessages("{}", stop="refusal")))
    assert (await llm.vote("sniper", "s", {}))["vote"] == "PASS"
    llm = LLM(cfg, db, client=SimpleNamespace(messages=FakeMessages("not json")))
    assert (await llm.vote("sniper", "s", {}))["vote"] == "PASS"


# ---------------------------------------------------------------- web
def test_health_starting_and_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "s3cret")
    c = TestClient(create_app({}))
    assert c.get("/health").status_code == 503
    assert c.get("/api/state").status_code == 401
    assert c.get("/").status_code == 200


async def test_safety_blocked_coin_not_requeued(rules_cfg, db):
    eng, dex = make_engine(rules_cfg, db, rep=safety_rep(mint_authority_revoked=False))
    s = snap(mint="BLK")
    await eng.evaluate(s)
    await eng._enqueue(s)
    assert eng.queue.qsize() == 0


async def test_concurrent_evaluations_respect_max_open(rules_cfg, db):
    import asyncio
    eng, dex = make_engine(rules_cfg, db)
    snaps = [snap(mint=f"C{i}", symbol=f"C{i}", vol_m5=40_000, buys_m5=500, sells_m5=200) for i in range(6)]
    for s in snaps:
        dex.snaps[s["mint"]] = s
    real_open = eng.broker.open

    async def slow_open(*a, **kw):  # a real DB round-trip leaves a window between risk check and insert
        await asyncio.sleep(0.05)
        return await real_open(*a, **kw)

    eng.broker.open = slow_open
    await asyncio.gather(*(eng.evaluate(s) for s in snaps))
    assert await db.open_count() == rules_cfg["sizing"]["max_open_positions"]


async def test_singleton_lock_blocks_second_instance(db):
    if db.is_sqlite and db.url.endswith(":memory:"):
        pytest.skip("no file to lock")
    from app.db import Database
    await db.acquire_singleton(key=777)
    other = Database(db.url)
    with pytest.raises(SystemExit):
        await other.acquire_singleton(key=777)
    await other.close()
