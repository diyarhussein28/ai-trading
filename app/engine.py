"""Orchestrator (blueprint 8): discovery -> hard filter -> safety gate -> social -> 3 agents -> consensus ->
confidence & size -> paper broker -> journal, lessons, checkpoints."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .agents.prompts import POST_MORTEM, language_rule
from .agents.team import ROSTER, build_team
from .consensus import decide
from .filters import market_filter, minor_flags, safety_gate
from .metrics import HISTORICAL_VERSIONS, calibration, evaluate_test, jsonable, summary
from .paper_broker import PaperBroker, exit_fill
from .risk import RiskManager, utc_midnight
from .sources.social import summarize
from .watchlist import Watchlist

log = logging.getLogger("engine")

EXIT_AR = {"TP": "جني ربح", "SL": "وقف خسارة", "TRAIL": "وقف متحرك", "TIME": "انتهى الوقت", "RUG": "سحب سيولة"}
VERDICT_AR = {"IN PROGRESS": "قيد التنفيذ", "PASSED": "ناجح", "FAILED": "فاشل",
              "STOPPED EARLY": "متوقف مبكراً", "INCONCLUSIVE": "غير حاسم"}


def _has(links: list[dict], *needles: str) -> bool:
    for l in links or []:
        blob = f"{l.get('type', '')} {l.get('label', '')} {l.get('url', '')}".lower()
        if any(n in blob for n in needles):
            return True
    return False


class Engine:
    def __init__(self, cfg: dict, db, dex, safety, social, stream, llm, alerts, demo: bool = False):
        self.cfg, self.db, self.dex, self.safety, self.social = cfg, db, dex, safety, social
        self.stream, self.llm, self.alerts, self.demo = stream, llm, alerts, demo
        self.version = cfg["version"]
        self.team = build_team(cfg, db, llm)
        self.broker = PaperBroker(cfg, db)
        self.risk = RiskManager(cfg, db)
        self.watch = Watchlist(cfg)
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.queued: set[str] = set()
        self.open_lock = asyncio.Lock()  # risk check + open must be atomic across eval workers
        self.blocked_until: dict[str, float] = {}  # safety/risk rejections: don't re-check every scan
        self.started_at = time.time()
        self.launches_seen = 0
        self._launch_base = 0
        self.last_scan_at = 0.0
        self.last_monitor_at = 0.0
        self.scanned = 0
        self.passed_filter = 0
        self.passed_safety = 0
        self.config_drift: str | None = None
        self.tasks: list[asyncio.Task] = []
        self._bg: set[asyncio.Task] = set()

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._launch_base = int(await self.db.meta_get("launches_seen", 0) or 0)
        key = f"config_hash:{self.version}"
        prev = await self.db.meta_get(key)
        cur = self.cfg["_meta"]["hash"]
        if prev and prev != cur:
            self.config_drift = (f"إعدادات {self.version} تغيّرت في نص الاختبار ({prev} ← {cur})؛ "
                                 f"غيّر قيمة version في ملف الإعدادات")
            log.warning(self.config_drift)
            await self.alerts.send("⚠️ " + self.config_drift)
        elif not prev:
            await self.db.meta_set(key, cur)
        if not await self.db.meta_get(f"test_started:{self.version}"):
            await self.db.meta_set(f"test_started:{self.version}", int(time.time()))
        if self.cfg["agents"]["backend"] == "llm" and self.llm is None:
            raise SystemExit("agents.backend is 'llm' but no Anthropic credentials were found. "
                             "Set ANTHROPIC_API_KEY or use agents.backend: rules.")
        if self.cfg["social"]["on_missing"] == "pass" and not getattr(self.social, "enabled", False):
            log.warning("X data disabled and social.on_missing=pass: Detective & Sniper will vote PASS on "
                        "every token, so NO trades will open. Set X_BEARER_TOKEN or social.on_missing: degrade.")
        frozen = await self.db.meta_get(f"lessons_frozen_at:{self.version}")
        if frozen is None:
            frozen = int(time.time())
            await self.db.meta_set(f"lessons_frozen_at:{self.version}", frozen)
        for a in self.team.values():
            a.lessons_frozen_at = frozen  # inject only lessons that existed when this version's test began

        stream_coro = self.stream.run_stream(self.on_launch_event) if self.demo else self.stream.run()
        self.tasks = [
            asyncio.create_task(stream_coro, name="stream"),
            asyncio.create_task(self._loop(self.scan_once, self.cfg["discovery"]["scan_interval_seconds"]), name="scan"),
            asyncio.create_task(self._loop(self.monitor_once, self.cfg["runtime"]["price_poll_seconds"]), name="monitor"),
            asyncio.create_task(self._loop(self.housekeeping, 60), name="housekeeping"),
        ]
        if self.cfg["discovery"].get("dexscreener_profiles") and not self.demo:
            self.tasks.append(asyncio.create_task(
                self._loop(self.profiles_once, self.cfg["discovery"]["profiles_poll_seconds"]), name="profiles"))
        for i in range(self.cfg["agents"]["max_concurrent_evaluations"]):
            self.tasks.append(asyncio.create_task(self.eval_worker(), name=f"eval-{i}"))
        mode = "ورقي" if self.cfg["mode"] == "paper" else self.cfg["mode"]
        agents = "Claude" if self.cfg["agents"]["backend"] == "llm" else "قواعد ثابتة"
        await self.alerts.send(f"🟢 البوت اشتغل · {self.version} · تداول {mode} · الوكلاء: {agents}")

    async def stop(self) -> None:
        for t in self.tasks + list(self._bg):
            t.cancel()
        await asyncio.gather(*self.tasks, *self._bg, return_exceptions=True)
        await self.db.meta_set("launches_seen", self._launch_base + self.launches_seen)

    async def _loop(self, fn, every: float) -> None:
        while True:
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s failed", getattr(fn, "__name__", fn))
            await asyncio.sleep(every)

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    # ------------------------------------------------------------------ discovery
    async def on_launch_event(self, ev: dict) -> None:
        self.launches_seen += 1
        if ev["event"] == "create" and not self.cfg["discovery"].get("pumpportal", True):
            return
        self.watch.add(ev["mint"], ev.get("symbol"), ev["event"])
        if ev["event"] == "migrate" or self.launches_seen % 25 == 0:
            await self.db.upsert_token(ev["mint"], ev.get("symbol"), ev.get("name"), ev["event"],
                                       creator=ev.get("creator"), migrated=ev["event"] == "migrate")

    async def profiles_once(self) -> None:
        for p in await self.dex.latest_profiles():
            self.watch.add(p["mint"], None, p["source"])

    async def scan_once(self) -> None:
        self.last_scan_at = time.time()
        due = self.watch.due(self.cfg["discovery"]["scan_batch_size"] * 2)
        if not due:
            return
        mints = [e.mint for e in due]
        try:
            snaps = await self.dex.snapshots(mints)
        except Exception as e:
            log.warning("scan failed: %s", e)
            return
        f = self.cfg["filters"]
        for m in mints:
            s = snaps.get(m)
            self.watch.checked(m, s)
            if not s:
                continue
            self.scanned += 1
            ok, reasons = market_filter(s, self.cfg)
            if not ok:
                if s["liquidity_usd"] >= f["min_liquidity_usd"] * 0.5:  # near misses only, keep the board readable
                    await self.db.save_candidate(m, s["symbol"], "filter", False, reasons, s["liquidity_usd"], s["vol_m5"])
                continue
            self.passed_filter += 1
            await self._enqueue(s)

    async def _enqueue(self, snap: dict) -> None:
        m = snap["mint"]
        if m in self.queued or self.blocked_until.get(m, 0) > time.time():
            return
        last = await self.db.last_decision_ts(m)
        if last and time.time() - last < self.cfg["discovery"]["reevaluate_minutes"] * 60:
            return
        if await self.db.has_open(m):
            return
        try:
            self.queue.put_nowait(snap)
            self.queued.add(m)
        except asyncio.QueueFull:
            log.warning("evaluation queue full, dropping %s", snap.get("symbol"))

    # ------------------------------------------------------------------ evaluation
    async def eval_worker(self) -> None:
        while True:
            snap = await self.queue.get()
            try:
                await self.evaluate(snap)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("evaluation of %s failed", snap.get("symbol"))
            finally:
                self.queued.discard(snap["mint"])
                self.queue.task_done()

    async def evaluate(self, snap: dict) -> None:
        mint, sym = snap["mint"], snap.get("symbol")
        ok, why = await self.risk.can_open(mint)
        if not ok:  # don't spend safety/X/LLM budget on a trade we could not take anyway
            self.blocked_until[mint] = time.time() + 60
            await self.db.save_candidate(mint, sym, "risk", False, [why], snap["liquidity_usd"], snap["vol_m5"])
            return

        rep = await self.safety.report(mint)
        safe, reasons = safety_gate(rep, self.cfg)
        await self.db.save_safety(mint, rep, safe, reasons)
        if not safe:
            self.blocked_until[mint] = time.time() + self.cfg["safety"].get("recheck_blocked_minutes", 10) * 60
            await self.db.save_candidate(mint, sym, "safety", False, reasons, snap["liquidity_usd"], snap["vol_m5"])
            await self.db.add_blackboard(mint, sym, "safety", "BLOCK", "; ".join(reasons))
            return
        self.passed_safety += 1
        flags = minor_flags(rep, self.cfg)

        # Social data only now - after the numeric filter and the safety gate (blueprint 11.3).
        self.team["detective"].state.status = "SCANNING"
        self.team["sniper"].state.status = "SCANNING"
        posts, social_status = (None, "disabled")
        if getattr(self.social, "enabled", False):
            posts, social_status = await self.social.fetch(mint, sym)
        sc = self.cfg["social"]
        soc = summarize(posts, sc["big_account_followers"], sc["aged_account_days"])
        soc["status"] = social_status

        links = (snap.get("socials") or []) + (snap.get("websites") or [])
        ctx: dict[str, Any] = {
            "mint": mint, "symbol": sym, "name": snap.get("name"), "dex": snap.get("dex"), "url": snap.get("url"),
            "market": {k: snap.get(k) for k in (
                "price_usd", "liquidity_usd", "vol_m5", "vol_h1", "buys_m5", "sells_m5", "buys_h1", "sells_h1",
                "price_change_m5", "price_change_h1", "fdv", "market_cap", "age_min")},
            "safety": {k: (rep or {}).get(k) for k in (
                "mint_authority_revoked", "freeze_authority_revoked", "top10_pct", "dev_pct", "bundle_pct",
                "lp_status", "lp_locked_pct", "quote_liquidity_usd", "holders", "rug_score", "insider_networks",
                "launchpad")},
            "minor_flags": flags,
            "profile": {"has_twitter": _has(links, "twitter", "x.com"), "has_telegram": _has(links, "telegram", "t.me"),
                        "has_website": bool(snap.get("websites")), "boosts": snap.get("boosts", 0)},
            "social": soc,
            "social_policy": sc["on_missing"],
            "posts": posts or [],
            "trend": self.watch.trend(mint),
        }
        ctx["market"]["vol5m_to_liquidity"] = round(snap["vol_m5"] / max(snap["liquidity_usd"], 1), 3)

        d = await decide(self.team, ctx, self.cfg, self.db)
        stored_ctx = {k: v for k, v in ctx.items() if k not in ("posts",)}
        decision_id = await self.db.save_decision(self.version, mint, sym, d.decision_key, d.unanimous, d.score,
                                                  d.size_sol, False, d.note, stored_ctx)
        await self.db.save_candidate(mint, sym, "agents", d.size_sol > 0, [d.note], snap["liquidity_usd"], snap["vol_m5"])
        if d.size_sol <= 0:
            return

        # Price moved while the agents were thinking: re-check against a fresh snapshot before "filling".
        fresh = await self.dex.snapshot(mint)
        if not fresh:
            await self.db.mark_decision_taken(decision_id, False, d.note + " | skipped: no fresh price")
            return
        still_ok, r2 = market_filter(fresh, self.cfg)
        drift = (fresh["price_usd"] / snap["price_usd"] - 1) * 100 if snap["price_usd"] else 0
        if not still_ok or drift > 15:
            await self.db.mark_decision_taken(decision_id, False, d.note + f" | skipped: moved {drift:+.1f}% {r2}")
            return
        async with self.open_lock:
            ok, why = await self.risk.can_open(mint)
            if not ok:
                await self.db.mark_decision_taken(decision_id, False, d.note + f" | skipped: {why}")
                return
            pos = await self.broker.open(fresh, d.size_sol, d.score, decision_id, self._sol_usd())
        if not pos:
            await self.db.mark_decision_taken(decision_id, False, d.note + " | skipped: already open")
            return
        await self.db.mark_decision_taken(decision_id, True, d.note)
        await self.db.add_blackboard(mint, sym, "broker", "OPEN",
                                     f"{d.size_sol:.4f} SOL بسعر ${fresh['price_usd']:.8f} (الثقة {d.score})")
        await self.alerts.send(f"🟢 فتح صفقة {sym} · {d.size_sol:.4f} SOL · الثقة {d.score} · "
                               f"السيولة ${fresh['liquidity_usd']:,.0f} · {fresh.get('url') or mint}")

    # ------------------------------------------------------------------ position monitoring
    def _sol_usd(self) -> float | None:
        return getattr(self.dex, "sol_usd", None)

    async def monitor_once(self) -> None:
        self.last_monitor_at = time.time()
        open_pos = await self.db.open_positions()
        if not open_pos:
            return
        try:
            snaps = await self.dex.snapshots([p["mint"] for p in open_pos])
        except Exception as e:  # an API outage is not a rug: skip this tick
            log.warning("monitor snapshot failed: %s", e)
            return
        for p in open_pos:
            closed = await self.broker.check(p, snaps.get(p["mint"]), self._sol_usd())
            if closed:
                await self.on_closed(closed)

    async def on_closed(self, pos: dict) -> None:
        held = (pos["closed_at"] - pos["opened_at"]) / 60
        icon = "✅" if pos["pnl_sol"] > 0 else "❌"
        why = EXIT_AR.get(pos["exit_reason"], pos["exit_reason"])
        msg = (f"{icon} إغلاق {pos['symbol']} · {why} · {pos['return_pct']:+.1f}% "
               f"({pos['pnl_sol']:+.5f} SOL) · المدة {held:.1f} دقيقة · أعلى ربح {pos['peak_return_pct'] or 0:+.1f}%")
        await self.db.add_blackboard(pos["mint"], pos["symbol"], "broker", "CLOSE", msg)
        await self.alerts.send(msg)
        await self.checkpoint()
        if self.llm is not None and self.cfg["lessons"]["post_mortem"]:
            self._spawn(self.post_mortem(pos))

    async def post_mortem(self, pos: dict) -> None:
        dec = await self.db.decision(pos["decision_id"]) if pos.get("decision_id") else None
        trade = {
            "symbol": pos["symbol"], "confidence": pos["confidence"], "size_sol": pos["size_sol"],
            "return_pct": round(pos["return_pct"], 2), "peak_return_pct": round(pos["peak_return_pct"] or 0, 2),
            "exit_reason": pos["exit_reason"], "held_minutes": round((pos["closed_at"] - pos["opened_at"]) / 60, 1),
            "context_at_entry": (dec or {}).get("context"),
            "votes": [{k: v[k] for k in ("agent", "vote", "score", "reason", "red_flags")}
                      for v in (await self.db.votes_for(dec["decision_key"]) if dec else [])],
        }
        for item in await self.llm.post_mortem(POST_MORTEM + language_rule(self.cfg), trade):
            await self.db.add_lesson(item["agent"], pos["mint"], pos["id"], item["lesson"])
            await self.db.add_blackboard(pos["mint"], pos["symbol"], item["agent"], "lesson", item["lesson"])

    # ------------------------------------------------------------------ test protocol
    async def operating_cost_usd(self) -> float:
        started = int(await self.db.meta_get(f"test_started:{self.version}", self.started_at) or self.started_at)
        spent = sum(v["usd"] for v in (await self.db.spend_by_service(started)).values())
        hosting = self.cfg["costs"].get("hosting_usd_per_month", 0) * (time.time() - started) / (30 * 86400)
        return spent + hosting

    async def test_status(self) -> dict:
        trades = await self.db.closed_positions(self.version)
        return evaluate_test(trades, self.cfg, await self.operating_cost_usd(), self._sol_usd())

    async def checkpoint(self) -> None:
        st = await self.test_status()
        n, every = st["summary"]["n"], self.cfg["test"]["checkpoint_every"]
        if n and n % every == 0 and not await self.db.has_report(self.version, "checkpoint", n):
            await self.db.add_report(self.version, "checkpoint", n, jsonable(st))
            s = st["summary"]
            lo, hi = s["ci95"]
            pf = s["profit_factor"]
            await self.alerts.send(
                f"📊 تقرير {self.version}: {n}/{st['planned']} صفقة · الإصابة {s['hit']:.0%} "
                f"(النطاق {lo:.0%}–{hi:.0%}) · Profit Factor {pf if pf is None else round(pf, 2)} · "
                f"الربح {s['pnl_sol']:+.4f} SOL · أسوأ صفقة {s['worst_pct']:+.1f}% · "
                f"الحكم: {VERDICT_AR.get(st['verdict'], st['verdict'])} (لا تغيّر أي إعداد أثناء الاختبار)")
        if st["early_stop"]:
            key = f"halted:{self.version}"
            if not await self.db.meta_get(key):
                await self.db.meta_set(key, "; ".join(st["early_stop"]))
                await self.alerts.send(f"🛑 {self.version}: انطبقت قاعدة الإيقاف المبكر ({'؛ '.join(st['early_stop'])}). "
                                       f"البوت وقف يدخل صفقات جديدة")
        if n >= st["planned"] and not await self.db.has_report(self.version, "final", n):
            await self.db.add_report(self.version, "final", n, jsonable(st))
            await self.alerts.send(f"🏁 {self.version} خلّص {n} صفقة · الحكم: {VERDICT_AR.get(st['verdict'], st['verdict'])}")

    # ------------------------------------------------------------------ housekeeping
    async def housekeeping(self) -> None:
        now = time.time()
        self.blocked_until = {m: t for m, t in self.blocked_until.items() if t > now}
        await self.db.meta_set("launches_seen", self._launch_base + self.launches_seen)
        stale = self.stream.stale_seconds()
        if stale > 120 and time.time() - self.started_at > 180:
            await self.alerts.send(f"⚠️ ما وصلت إطلاقات جديدة من PumpPortal من {stale:.0f} ثانية", "stream_stale", 900)
        if getattr(self.dex, "http_429", 0) > 20:
            await self.alerts.send(f"⚠️ DexScreener رفض {self.dex.http_429} طلب (تجاوز حد الطلبات 429)", "dex429", 1800)
            self.dex.http_429 = 0
        guard = getattr(self.social, "guard", None)
        if guard is not None and (await guard.status("x_api"))["exhausted"]:
            await self.alerts.send("⚠️ خلصت ميزانية X؛ المحقق والقنّاص يرفضون كل شيء لين تتجدد الميزانية", "xbudget", 3600)
        if int(time.time()) % 3600 < 60:
            await self.db.prune(self.cfg["runtime"]["retention_days"])

    def healthy(self) -> tuple[bool, dict]:
        lim = self.cfg["runtime"]["heartbeat_stale_seconds"]
        now = time.time()
        checks = {
            "scan_loop_age_s": round(now - self.last_scan_at, 1) if self.last_scan_at else None,
            "monitor_loop_age_s": round(now - self.last_monitor_at, 1) if self.last_monitor_at else None,
            "tasks_alive": all(not t.done() for t in self.tasks),
        }
        warming = now - self.started_at < lim
        ok = checks["tasks_alive"] and (warming or (
            (checks["scan_loop_age_s"] or 1e9) < lim and (checks["monitor_loop_age_s"] or 1e9) < lim))
        return ok, checks

    # ------------------------------------------------------------------ dashboard state
    async def state(self) -> dict:
        trades = await self.db.closed_positions(self.version)
        st = await self.test_status()
        open_pos = await self.db.open_positions()
        for p in open_pos:
            entry, last = p["entry_price"], p.get("last_price") or p["entry_mid_price"]
            p["unrealized_pct"] = (exit_fill(self.cfg, last, p["size_sol"], self._sol_usd(), p.get("last_liq") or 1)
                                   / entry - 1) * 100
            p["held_min"] = (time.time() - p["opened_at"]) / 60
        lessons = await self.db.latest_lessons()
        agents = []
        for name, a in self.team.items():
            agents.append({"key": name, **ROSTER[name], "status": a.state.status, "thought": a.state.thought,
                           "buys": a.state.buys, "passes": a.state.passes,
                           "lesson": (lessons.get(name) or {}).get("lesson")})
        versions = list(HISTORICAL_VERSIONS)
        for v in sorted(set(await self.db.versions_seen()) | {self.version}):
            s = summary(await self.db.closed_positions(v))
            versions.append({"version": v + " (مباشر)", "closed": s["n"], "wins": s["wins"], "hit": s["hit"],
                             "pnl_sol": s["pnl_sol"], "note": f"{s['n']} من {self.cfg['test']['planned_trades']} مخطط لها"
                             if v == self.version else ""})
        spend = await self.db.spend_by_service()
        guard = getattr(self.social, "guard", None)
        ok, health = self.healthy()
        return jsonable({
            "version": self.version, "mode": self.cfg["mode"].upper(), "backend": self.cfg["agents"]["backend"],
            "demo": self.demo, "config_hash": self.cfg["_meta"]["hash"], "config_drift": self.config_drift,
            "uptime_min": (time.time() - self.started_at) / 60,
            "launches_seen": self._launch_base + self.launches_seen,
            "pnl_today_sol": await self.db.realized_since(utc_midnight()),
            "sol_usd": self._sol_usd(),
            "pipeline": {"scanned": self.scanned, "passed_filter": self.passed_filter,
                         "passed_safety": self.passed_safety, "queue": self.queue.qsize(), **self.watch.stats(),
                         **await self.db.decision_stats(int(self.started_at))},
            "agents": agents,
            "lesson_count": await self.db.lesson_count(),
            "open_positions": open_pos,
            "trades": trades[-50:][::-1],
            "test": st,
            "calibration": calibration(trades, self.cfg["exits"]["take_profit_pct"]),
            "versions": versions,
            "blackboard": await self.db.recent_blackboard(40),
            "candidates": await self.db.recent_candidates(30),
            "costs": {"by_service": spend, "operating_usd": await self.operating_cost_usd(),
                      "x_budget": await guard.status("x_api") if guard else None,
                      "pnl_usd": st["summary"]["pnl_sol"] * self._sol_usd() if self._sol_usd() else None},
            "social_enabled": bool(getattr(self.social, "enabled", False)),
            "social_policy": self.cfg["social"]["on_missing"],
            "risk": {"paused": await self.db.meta_get("paused", False),
                     "halted": await self.db.meta_get(f"halted:{self.version}"),
                     "kill_switch_until": await self.risk.kill_switch_until()},
            "health": {"ok": ok, **health, "stream_connected": getattr(self.stream, "connected", None),
                       "stream_stale_s": round(self.stream.stale_seconds(), 1)},
            "reports": await self.db.recent_reports(5),
        })
