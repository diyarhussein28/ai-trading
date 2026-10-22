"""Storage layer (blueprint 9.2). SQLAlchemy Core async: SQLite locally, Postgres on Railway."""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, Float, Index, Integer, MetaData, String, Table, Text,
    and_, delete, func, insert, select, update,
)
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

md = MetaData()
PK = BigInteger().with_variant(Integer, "sqlite")  # SQLite only autoincrements INTEGER PRIMARY KEY

tokens = Table(
    "tokens", md,
    Column("mint", String, primary_key=True), Column("symbol", String), Column("name", String),
    Column("creator", String), Column("first_seen_at", BigInteger), Column("migrated_at", BigInteger),
    Column("source", String),
)
snapshots = Table(
    "snapshots", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("mint", String, index=True),
    Column("ts", BigInteger), Column("price_usd", Float), Column("liquidity_usd", Float),
    Column("vol_m5", Float), Column("vol_h1", Float), Column("buys_m5", Integer), Column("sells_m5", Integer),
    Column("price_change_m5", Float), Column("fdv", Float), Column("age_min", Float), Column("raw", JSON),
)
safety_reports = Table(
    "safety_reports", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("mint", String, index=True),
    Column("ts", BigInteger), Column("mint_authority_revoked", Boolean), Column("freeze_authority_revoked", Boolean),
    Column("top10_pct", Float), Column("dev_pct", Float), Column("lp_status", String), Column("lp_locked_pct", Float),
    Column("bundle_pct", Float), Column("holders", Integer), Column("rug_score", Float), Column("ok", Boolean),
    Column("reasons", JSON), Column("raw", JSON),
)
candidates = Table(  # "CANDIDATE BOARD"
    "candidates", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("mint", String, index=True),
    Column("symbol", String), Column("ts", BigInteger, index=True), Column("stage", String),
    Column("passed", Boolean), Column("reasons", JSON), Column("liquidity_usd", Float), Column("vol_m5", Float),
)
social_cache = Table(
    "social_cache", md,
    Column("query", String, primary_key=True), Column("fetched_at", BigInteger), Column("posts", JSON),
    Column("cost_units", Integer),
)
votes = Table(
    "votes", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("team", String), Column("version", String),
    Column("mint", String, index=True), Column("ts", BigInteger), Column("decision_key", String, index=True),
    Column("agent", String), Column("vote", String), Column("score", Integer), Column("reason", Text),
    Column("red_flags", JSON),
)
decisions = Table(
    "decisions", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("team", String), Column("version", String),
    Column("mint", String, index=True), Column("symbol", String), Column("ts", BigInteger, index=True),
    Column("decision_key", String), Column("consensus", Boolean), Column("confidence", Integer),
    Column("size_sol", Float), Column("taken", Boolean), Column("note", Text), Column("context", JSON),
)
positions = Table(
    "positions", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("team", String), Column("version", String),
    Column("mint", String), Column("symbol", String), Column("decision_id", BigInteger),
    Column("confidence", Integer), Column("size_sol", Float),
    Column("opened_at", BigInteger), Column("closed_at", BigInteger, nullable=True),
    Column("entry_price", Float), Column("entry_mid_price", Float), Column("entry_liq", Float),
    Column("last_price", Float), Column("last_liq", Float), Column("missing_polls", Integer, default=0),
    Column("exit_price", Float), Column("peak_return_pct", Float, default=0.0),
    Column("return_pct", Float), Column("fees_sol", Float), Column("pnl_sol", Float),
    Column("exit_reason", String), Column("mode", String, default="paper"), Column("config_hash", String),
)
Index(
    "one_open_per_token", positions.c.team, positions.c.mint, unique=True,
    sqlite_where=positions.c.closed_at.is_(None), postgresql_where=positions.c.closed_at.is_(None),
)
lessons = Table(
    "lessons", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("team", String), Column("agent", String),
    Column("ts", BigInteger), Column("mint", String), Column("position_id", BigInteger),
    Column("lesson", Text), Column("active", Boolean, default=True),
)
blackboard = Table(
    "blackboard", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("team", String), Column("ts", BigInteger, index=True),
    Column("mint", String), Column("symbol", String), Column("agent", String), Column("topic", String),
    Column("note", Text),
)
spend_ledger = Table(  # X / LLM / RPC / hosting costs
    "spend_ledger", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("ts", BigInteger, index=True),
    Column("service", String, index=True), Column("units", Integer), Column("usd", Float), Column("note", String),
)
reports = Table(
    "reports", md,
    Column("id", PK, primary_key=True, autoincrement=True), Column("ts", BigInteger), Column("version", String),
    Column("kind", String), Column("trades", Integer), Column("body", JSON),
)
meta = Table("meta", md, Column("key", String, primary_key=True), Column("value", JSON))


def _row(r) -> dict[str, Any]:
    return dict(r._mapping) if r is not None else None


def now() -> int:
    return int(time.time())


def default_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        Path("data").mkdir(exist_ok=True)
        return "sqlite+aiosqlite:///data/agents.db"
    # Railway hands out postgres:// or postgresql:// URLs; point them at the async driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


class Database:
    def __init__(self, url: str | None = None, team: str = "claude"):
        self.url = url or default_url()
        self.team = team
        kw: dict[str, Any] = {}
        if self.url.startswith("sqlite"):
            kw["connect_args"] = {"timeout": 30}
        self.engine: AsyncEngine = create_async_engine(self.url, **kw)
        self.is_sqlite = self.url.startswith("sqlite")
        self._lock_conn: AsyncConnection | None = None
        self._lock_file = None

    # ------------------------------------------------------------------ lifecycle
    async def init(self) -> None:
        async with self.engine.begin() as c:
            if self.is_sqlite:
                await c.exec_driver_sql("PRAGMA journal_mode=WAL")
            await c.run_sync(md.create_all)

    async def close(self) -> None:
        if self._lock_conn is not None:
            await self._lock_conn.close()
        if self._lock_file is not None:
            self._lock_file.close()
        await self.engine.dispose()

    async def acquire_singleton(self, key: int = 424242) -> None:
        """Blueprint 12.8: only one process may trade, or every bet gets duplicated (the V1/V7 bug)."""
        if self.is_sqlite:
            path = self.url.split("///", 1)[-1]
            if path in (":memory:", ""):
                return
            self._lock_file = open(path + ".lock", "w")
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("Another instance holds the lock - exiting (prevents duplicate bets).")
            return
        self._lock_conn = await self.engine.connect()
        ok = (await self._lock_conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({int(key)})")).scalar()
        if not ok:
            raise SystemExit("Another instance holds the lock - exiting (prevents duplicate bets).")

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as c:
                await c.execute(select(1))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ generic helpers
    async def _exec(self, stmt):
        async with self.engine.begin() as c:
            return await c.execute(stmt)

    async def _all(self, stmt) -> list[dict]:
        async with self.engine.connect() as c:
            return [dict(r._mapping) for r in (await c.execute(stmt)).fetchall()]

    async def _one(self, stmt) -> dict | None:
        async with self.engine.connect() as c:
            return _row((await c.execute(stmt)).first())

    async def _scalar(self, stmt):
        async with self.engine.connect() as c:
            return (await c.execute(stmt)).scalar()

    # ------------------------------------------------------------------ meta / counters
    async def meta_get(self, key: str, default=None):
        r = await self._one(select(meta.c.value).where(meta.c.key == key))
        return r["value"] if r else default

    async def meta_set(self, key: str, value) -> None:
        async with self.engine.begin() as c:
            res = await c.execute(update(meta).where(meta.c.key == key).values(value=value))
            if res.rowcount == 0:
                await c.execute(insert(meta).values(key=key, value=value))

    async def meta_incr(self, key: str, n: int = 1) -> int:
        v = int(await self.meta_get(key, 0) or 0) + n
        await self.meta_set(key, v)
        return v

    # ------------------------------------------------------------------ tokens & market data
    async def upsert_token(self, mint: str, symbol: str | None, name: str | None, source: str,
                           creator: str | None = None, migrated: bool = False) -> bool:
        """Returns True if the token is new."""
        async with self.engine.begin() as c:
            existing = (await c.execute(select(tokens.c.mint).where(tokens.c.mint == mint))).first()
            if existing is None:
                await c.execute(insert(tokens).values(
                    mint=mint, symbol=symbol, name=name, creator=creator, source=source,
                    first_seen_at=now(), migrated_at=now() if migrated else None))
                return True
            vals: dict[str, Any] = {}
            if migrated:
                vals["migrated_at"] = now()
            if symbol:
                vals["symbol"] = symbol
            if vals:
                await c.execute(update(tokens).where(tokens.c.mint == mint).values(**vals))
            return False

    async def save_snapshot(self, s: dict) -> None:
        await self._exec(insert(snapshots).values(
            mint=s["mint"], ts=s["ts"], price_usd=s["price_usd"], liquidity_usd=s["liquidity_usd"],
            vol_m5=s["vol_m5"], vol_h1=s["vol_h1"], buys_m5=s["buys_m5"], sells_m5=s["sells_m5"],
            price_change_m5=s["price_change_m5"], fdv=s.get("fdv"), age_min=s.get("age_min"),
            raw={k: s.get(k) for k in ("dex", "pair", "url", "socials", "websites", "market_cap")}))

    async def save_safety(self, mint: str, rep: dict | None, ok: bool, reasons: list[str]) -> None:
        rep = rep or {}
        await self._exec(insert(safety_reports).values(
            mint=mint, ts=now(), ok=ok, reasons=reasons,
            mint_authority_revoked=rep.get("mint_authority_revoked"),
            freeze_authority_revoked=rep.get("freeze_authority_revoked"),
            top10_pct=rep.get("top10_pct"), dev_pct=rep.get("dev_pct"), lp_status=rep.get("lp_status"),
            lp_locked_pct=rep.get("lp_locked_pct"), bundle_pct=rep.get("bundle_pct"),
            holders=rep.get("holders"), rug_score=rep.get("rug_score"),
            raw={k: rep.get(k) for k in ("risks", "source", "rugged")}))

    async def save_candidate(self, mint: str, symbol: str | None, stage: str, passed: bool,
                             reasons: list[str], liq: float | None = None, vol: float | None = None) -> None:
        await self._exec(insert(candidates).values(
            mint=mint, symbol=symbol, ts=now(), stage=stage, passed=passed, reasons=reasons,
            liquidity_usd=liq, vol_m5=vol))

    async def recent_candidates(self, limit: int = 40) -> list[dict]:
        return await self._all(select(candidates).order_by(candidates.c.id.desc()).limit(limit))

    # ------------------------------------------------------------------ social cache
    async def social_get(self, query: str, max_age_s: int) -> list | None:
        r = await self._one(select(social_cache).where(social_cache.c.query == query))
        if r and now() - r["fetched_at"] <= max_age_s:
            return r["posts"]
        return None

    async def social_put(self, query: str, posts: list, units: int) -> None:
        async with self.engine.begin() as c:
            await c.execute(delete(social_cache).where(social_cache.c.query == query))
            await c.execute(insert(social_cache).values(query=query, fetched_at=now(), posts=posts, cost_units=units))

    # ------------------------------------------------------------------ spend ledger
    async def insert_spend(self, service: str, units: int, usd: float, note: str = "") -> None:
        await self._exec(insert(spend_ledger).values(ts=now(), service=service, units=units, usd=usd, note=note[:200]))

    async def spend_since(self, service: str, since_ts: int) -> float:
        v = await self._scalar(select(func.coalesce(func.sum(spend_ledger.c.usd), 0.0)).where(
            and_(spend_ledger.c.service == service, spend_ledger.c.ts >= since_ts)))
        return float(v or 0.0)

    async def spend_by_service(self, since_ts: int = 0) -> dict[str, dict]:
        rows = await self._all(
            select(spend_ledger.c.service, func.sum(spend_ledger.c.usd).label("usd"),
                   func.sum(spend_ledger.c.units).label("units"))
            .where(spend_ledger.c.ts >= since_ts).group_by(spend_ledger.c.service))
        return {r["service"]: {"usd": float(r["usd"] or 0), "units": int(r["units"] or 0)} for r in rows}

    # ------------------------------------------------------------------ votes / decisions / blackboard
    async def save_vote(self, version: str, mint: str, decision_key: str, agent: str, v: dict) -> None:
        await self._exec(insert(votes).values(
            team=self.team, version=version, mint=mint, ts=now(), decision_key=decision_key, agent=agent,
            vote=v["vote"], score=int(v["score"]), reason=v.get("reason", ""), red_flags=v.get("red_flags", [])))

    async def votes_for(self, decision_key: str) -> list[dict]:
        return await self._all(select(votes).where(votes.c.decision_key == decision_key).order_by(votes.c.id))

    async def save_decision(self, version: str, mint: str, symbol: str | None, decision_key: str,
                            consensus: bool, confidence: int, size_sol: float, taken: bool,
                            note: str = "", context: dict | None = None) -> int:
        res = await self._exec(insert(decisions).values(
            team=self.team, version=version, mint=mint, symbol=symbol, ts=now(), decision_key=decision_key,
            consensus=consensus, confidence=confidence, size_sol=size_sol, taken=taken, note=note,
            context=context).returning(decisions.c.id))
        return int(res.scalar())

    async def mark_decision_taken(self, decision_id: int, taken: bool, note: str) -> None:
        await self._exec(update(decisions).where(decisions.c.id == decision_id).values(taken=taken, note=note))

    async def decision(self, decision_id: int) -> dict | None:
        return await self._one(select(decisions).where(decisions.c.id == decision_id))

    async def last_decision_ts(self, mint: str) -> int | None:
        return await self._scalar(select(func.max(decisions.c.ts)).where(
            and_(decisions.c.mint == mint, decisions.c.team == self.team)))

    async def decision_stats(self, since_ts: int) -> dict:
        rows = await self._all(select(decisions.c.consensus, decisions.c.taken, func.count().label("n"))
                               .where(decisions.c.ts >= since_ts).group_by(decisions.c.consensus, decisions.c.taken))
        out = {"evaluated": 0, "consensus": 0, "taken": 0}
        for r in rows:
            out["evaluated"] += r["n"]
            out["consensus"] += r["n"] if r["consensus"] else 0
            out["taken"] += r["n"] if r["taken"] else 0
        return out

    async def add_blackboard(self, mint: str, symbol: str | None, agent: str, topic: str, note: str) -> None:
        await self._exec(insert(blackboard).values(
            team=self.team, ts=now(), mint=mint, symbol=symbol, agent=agent, topic=topic, note=note[:500]))

    async def recent_blackboard(self, limit: int = 40) -> list[dict]:
        return await self._all(select(blackboard).order_by(blackboard.c.id.desc()).limit(limit))

    # ------------------------------------------------------------------ positions
    async def insert_position(self, **vals) -> dict | None:
        vals.setdefault("team", self.team)
        vals.setdefault("missing_polls", 0)
        vals.setdefault("peak_return_pct", 0.0)
        try:
            res = await self._exec(insert(positions).values(**vals).returning(positions.c.id))
        except Exception as e:  # unique index -> already open for this token
            if "one_open_per_token" in str(e) or "UNIQUE" in str(e).upper():
                return None
            raise
        return await self.position(int(res.scalar()))

    async def position(self, pid: int) -> dict | None:
        return await self._one(select(positions).where(positions.c.id == pid))

    async def open_positions(self) -> list[dict]:
        return await self._all(select(positions).where(
            and_(positions.c.team == self.team, positions.c.closed_at.is_(None))).order_by(positions.c.id))

    async def has_open(self, mint: str) -> bool:
        return (await self._scalar(select(func.count()).where(and_(
            positions.c.team == self.team, positions.c.mint == mint, positions.c.closed_at.is_(None))))) > 0

    async def open_count(self) -> int:
        return int(await self._scalar(select(func.count()).where(and_(
            positions.c.team == self.team, positions.c.closed_at.is_(None)))) or 0)

    async def update_position_mark(self, pid: int, **vals) -> None:
        await self._exec(update(positions).where(positions.c.id == pid).values(**vals))

    async def close_position(self, pid: int, exit_price: float, return_pct: float, pnl_sol: float,
                             fees_sol: float, reason: str, peak: float | None, closed_at: int) -> dict | None:
        async with self.engine.begin() as c:
            res = await c.execute(update(positions).where(
                and_(positions.c.id == pid, positions.c.closed_at.is_(None))).values(
                exit_price=exit_price, return_pct=return_pct, pnl_sol=pnl_sol, fees_sol=fees_sol,
                exit_reason=reason, peak_return_pct=peak, closed_at=closed_at))
            if res.rowcount == 0:
                return None  # already closed by someone else
        return await self.position(pid)

    async def closed_positions(self, version: str | None = None, limit: int | None = None) -> list[dict]:
        q = select(positions).where(and_(positions.c.team == self.team, positions.c.closed_at.is_not(None)))
        if version:
            q = q.where(positions.c.version == version)
        q = q.order_by(positions.c.closed_at.desc(), positions.c.id.desc())
        if limit:
            q = q.limit(limit)
        rows = await self._all(q)
        return rows[::-1]  # chronological

    async def realized_since(self, since_ts: int) -> float:
        v = await self._scalar(select(func.coalesce(func.sum(positions.c.pnl_sol), 0.0)).where(and_(
            positions.c.team == self.team, positions.c.closed_at >= since_ts)))
        return float(v or 0.0)

    async def last_exit_ts(self, mint: str) -> int | None:
        return await self._scalar(select(func.max(positions.c.closed_at)).where(and_(
            positions.c.team == self.team, positions.c.mint == mint)))

    async def versions_seen(self) -> list[str]:
        rows = await self._all(select(positions.c.version).distinct())
        return [r["version"] for r in rows if r["version"]]

    # ------------------------------------------------------------------ lessons
    async def add_lesson(self, agent: str, mint: str, position_id: int | None, lesson: str) -> None:
        await self._exec(insert(lessons).values(
            team=self.team, agent=agent, ts=now(), mint=mint, position_id=position_id, lesson=lesson[:600], active=True))

    async def active_lessons(self, agent: str, limit: int = 10, before_ts: int | None = None) -> list[str]:
        q = select(lessons.c.lesson).where(and_(
            lessons.c.team == self.team, lessons.c.agent == agent, lessons.c.active.is_(True)))
        if before_ts is not None:
            q = q.where(lessons.c.ts <= before_ts)
        rows = await self._all(q.order_by(lessons.c.id.desc()).limit(limit))
        return [r["lesson"] for r in rows]

    async def latest_lessons(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        rows = await self._all(select(lessons).where(lessons.c.team == self.team).order_by(lessons.c.id.desc()).limit(60))
        for r in rows:
            out.setdefault(r["agent"], r)
        return out

    async def lesson_count(self) -> int:
        return int(await self._scalar(select(func.count()).select_from(lessons)) or 0)

    # ------------------------------------------------------------------ reports
    async def add_report(self, version: str, kind: str, trades: int, body: dict) -> None:
        await self._exec(insert(reports).values(ts=now(), version=version, kind=kind, trades=trades, body=body))

    async def has_report(self, version: str, kind: str, trades: int) -> bool:
        return (await self._scalar(select(func.count()).where(and_(
            reports.c.version == version, reports.c.kind == kind, reports.c.trades == trades)))) > 0

    async def recent_reports(self, limit: int = 10) -> list[dict]:
        return await self._all(select(reports).order_by(reports.c.id.desc()).limit(limit))

    # ------------------------------------------------------------------ housekeeping
    async def prune(self, retention_days: int) -> None:
        cutoff = now() - retention_days * 86400
        async with self.engine.begin() as c:
            for t in (candidates, blackboard, snapshots, safety_reports):
                await c.execute(delete(t).where(t.c.ts < cutoff))
            await c.execute(delete(social_cache).where(social_cache.c.fetched_at < cutoff))
