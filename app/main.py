"""Entry point.

    python -m app.main run       # live market data, paper trading (default)
    python -m app.main demo      # synthetic market + rule agents, no keys, no network
    python -m app.main report    # print the 100-trade test status from the database
    python -m app.main check MINT  # one-shot: snapshot + filter + safety gate for a real token
    python -m app.main doctor    # check every key in .env against its service (free calls only, nothing printed)
    python -m app.main simulate --trades 100 --speed 30
                                 # run the 100-trade protocol on the synthetic market with a fast clock
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys

import uvicorn

from .alerts import Alerter
from .config import DEMO_OVERRIDES, load_config, load_dotenv
from .db import Database
from .engine import Engine
from .filters import market_filter, minor_flags, safety_gate
from .metrics import jsonable
from .paper_broker import assert_paper_mode
from .web import create_app

log = logging.getLogger("main")


def setup_logging() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    for noisy in ("httpx", "httpcore", "httpx2", "httpcore2", "anthropic", "websockets", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def make_llm(cfg: dict, db):
    if cfg["agents"]["backend"] != "llm":
        return None
    try:
        from .agents.llm import LLM
        return LLM(cfg, db)
    except Exception as e:  # missing credentials raise at client construction in some SDK versions
        log.error("could not create Anthropic client: %s", e)
        return None


async def serve(engine_ref: dict) -> uvicorn.Server:
    port = int(os.environ.get("PORT", "8080"))
    server = uvicorn.Server(uvicorn.Config(create_app(engine_ref), host="0.0.0.0", port=port,
                                           log_level="warning", lifespan="off"))
    return server


async def run(demo: bool, db_url: str | None = None) -> None:
    cfg = load_config(overrides=DEMO_OVERRIDES if demo else None)
    assert_paper_mode(cfg)
    if demo and not db_url and not os.environ.get("DATABASE_URL"):
        os.makedirs("data", exist_ok=True)
        db_url = "sqlite+aiosqlite:///data/demo.db"
    db = Database(db_url, team=cfg.get("team", "claude"))
    await db.init()
    if cfg["runtime"].get("single_instance", True):
        await db.acquire_singleton()

    alerts = Alerter()
    if demo:
        from .sources.demo import DemoMarket
        market = DemoMarket()
        dex = safety = social = stream = market
    else:
        from .sources.dexscreener import DexScreener
        from .sources.safety import SafetyClient
        from .sources.social import SocialClient
        dex = DexScreener()
        safety = SafetyClient(os.environ.get("SOLANA_RPC_URL") or None, cfg["safety"]["cache_seconds"])
        social = SocialClient(db, cfg, os.environ.get("X_BEARER_TOKEN") or None)
        stream = None  # created below so it can call back into the engine

    engine_ref: dict = {}
    engine = Engine(cfg, db, dex, safety, social, stream, make_llm(cfg, db), alerts, demo=demo)
    if not demo:
        from .sources.pumpportal import PumpPortalStream
        engine.stream = PumpPortalStream(engine.on_launch_event)
    await engine.start()
    engine_ref["engine"] = engine

    server = await serve(engine_ref)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    web_task = asyncio.create_task(server.serve())
    log.info("dashboard on http://localhost:%s  (version %s, %s, agents=%s)",
             os.environ.get("PORT", "8080"), cfg["version"], "DEMO" if demo else cfg["mode"], cfg["agents"]["backend"])
    await stop.wait()
    log.info("shutting down - open positions stay in the database and resume on restart")
    server.should_exit = True
    await engine.stop()
    await web_task
    for c in {id(x): x for x in (dex, safety, social, alerts)}.values():
        try:
            await c.aclose()
        except Exception:
            pass
    await db.close()


# Real V7 settings, synthetic data. Only what a fast clock or an offline market forces is changed.
SIM_OVERRIDES = {
    "version": "V7-sim",
    "agents": {"backend": "rules"},
    "lessons": {"post_mortem": False},
    "discovery": {"scan_interval_seconds": 0.2},
    "runtime": {"price_poll_seconds": 0.1},
    # Keep going to the planned trade count; the verdict still reports any early-stop rule that fired.
    "risk": {"auto_stop_on_early_stop_rule": False, "kill_switch_pause_hours": 2},
}


async def simulate(trades: int, speed: float, seed: int, max_minutes: float) -> None:
    import time as _time
    from .sources.demo import DemoMarket

    real = _time.time
    t0 = real()
    if speed > 1:  # every module calls time.time(), so the whole engine runs on the fast clock
        _time.time = lambda: t0 + (real() - t0) * speed
    cfg = load_config(overrides=SIM_OVERRIDES)
    os.makedirs("data", exist_ok=True)
    path = f"data/sim-{int(t0)}.db"
    db = Database(f"sqlite+aiosqlite:///{path}", team=cfg.get("team", "claude"))
    await db.init()
    market = DemoMarket(seed=seed, launches_per_minute=120)
    alerts = Alerter()
    alerts.tg_token = alerts.discord = None  # a simulation never pings your phone
    engine = Engine(cfg, db, market, market, market, market, None, alerts, demo=True)
    await engine.start()
    last = -1
    try:
        while real() - t0 < max_minutes * 60:
            await asyncio.sleep(2)
            n = len(await db.closed_positions(cfg["version"]))
            if n // 10 != last // 10 or n >= trades:
                st = await engine.test_status()
                s = st["summary"]
                print(f"[{(real() - t0) / 60:5.1f} min real | {(_time.time() - t0) / 3600:5.1f} h sim] "
                      f"{n:3d}/{trades} trades · hit {s['hit']:.0%} · PnL {s['pnl_sol']:+.4f} SOL", flush=True)
                last = n
            if n >= trades:
                break
    finally:
        await engine.stop()
    st = await engine.test_status()
    trades_rows = await db.closed_positions(cfg["version"])
    print(json.dumps(jsonable({k: st[k] for k in ("verdict", "progress", "planned", "summary", "criteria",
                                                   "early_stop", "calibration")}), indent=2))
    print("reports written:", [(r["kind"], r["trades"]) for r in await db.recent_reports(20)][::-1])
    print("database:", path, "| trades:", len(trades_rows))
    await db.close()
    _time.time = real


async def doctor() -> bool:
    """Verify each credential with a free call. Never prints a secret."""
    import httpx
    from urllib.parse import urlparse

    ok_all = True

    def line(ok: bool | None, name: str, msg: str) -> None:
        nonlocal ok_all
        icon = {True: "✅", False: "❌", None: "⚪"}[ok]
        if ok is False:
            ok_all = False
        print(f"{icon} {name}: {msg}")

    def mask(v: str) -> str:
        return f"…{v[-4:]}" if len(v) > 8 else "(قصير جداً)"

    env = lambda k: (os.environ.get(k) or "").strip()
    cfg = load_config()
    print(f"الإعدادات: {cfg['_meta']['path']} · النسخة {cfg['version']} · الوضع {cfg['mode']} · الوكلاء {cfg['agents']['backend']}\n")

    async with httpx.AsyncClient(timeout=15) as c:
        # Anthropic: list the two models (no tokens spent)
        key = env("ANTHROPIC_API_KEY")
        if not key:
            line(cfg["agents"]["backend"] != "llm" and None, "Anthropic", "المفتاح ناقص (ANTHROPIC_API_KEY)")
        else:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key, max_retries=1, timeout=15)
            for var, default in (("CLAUDE_VOTE_MODEL", "claude-haiku-5-5"), ("CLAUDE_REVIEW_MODEL", "claude-opus-5-5")):
                model = env(var) or default
                try:
                    await client.models.retrieve(model)
                    line(True, f"Anthropic ({var})", f"المفتاح {mask(key)} شغّال والنموذج {model} متاح")
                except anthropic.AuthenticationError:
                    line(False, "Anthropic", f"المفتاح {mask(key)} مرفوض. انسخه من جديد من console.anthropic.com")
                    break
                except anthropic.NotFoundError:
                    line(False, f"Anthropic ({var})", f"النموذج {model} غير متاح لحسابك")
                except anthropic.APIError as e:
                    line(False, "Anthropic", f"خطأ: {type(e).__name__}")
            await client.close()

        # X: the usage endpoint authenticates the token without reading (or paying for) any post
        tok = env("X_BEARER_TOKEN")
        if not tok:
            line(False if cfg["social"]["on_missing"] == "pass" else None, "X",
                 "التوكن ناقص، فالمحقق والقنّاص راح يرفضون كل عملة" if cfg["social"]["on_missing"] == "pass"
                 else "التوكن ناقص (وضع degrade مفعّل)")
        else:
            try:
                r = await c.get("https://api.x.com/2/usage/tweets", headers={"Authorization": f"Bearer {tok}"})
                if r.status_code == 200:
                    line(True, "X", f"التوكن {mask(tok)} شغّال")
                elif r.status_code == 401:
                    line(False, "X", f"التوكن {mask(tok)} مرفوض (401). انسخ Bearer Token من جديد")
                elif r.status_code in (402, 403):
                    detail = (r.json().get("detail") or r.json().get("title") or "") if r.headers.get("content-type", "").startswith("application/json") else ""
                    line(False, "X", f"التوكن صحيح لكن الوصول مرفوض ({r.status_code}): {detail[:160]} - غالباً تحتاج رصيد (Credits)")
                else:
                    line(False, "X", f"رد غير متوقع {r.status_code}")
            except httpx.HTTPError as e:
                line(False, "X", f"ما قدرنا نتصل: {type(e).__name__}")

        # Telegram: getMe + getChat (sends nothing)
        bt, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
        if not bt and not chat:
            line(None, "Telegram", "غير مضبوط (اختياري)")
        elif not (bt and chat):
            line(False, "Telegram", "لازم TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID مع بعض")
        else:
            try:
                me = (await c.get(f"https://api.telegram.org/bot{bt}/getMe")).json()
                if not me.get("ok"):
                    line(False, "Telegram", "توكن البوت مرفوض. انسخه من جديد من @BotFather")
                else:
                    ch = (await c.get(f"https://api.telegram.org/bot{bt}/getChat", params={"chat_id": chat})).json()
                    if ch.get("ok"):
                        line(True, "Telegram", f"البوت @{me['result'].get('username')} يقدر يرسل للمحادثة {mask(chat)}")
                    else:
                        line(False, "Telegram", f"البوت @{me['result'].get('username')} شغّال، لكن رقم المحادثة غلط أو ما راسلته "
                                                f"(افتح البوت واكتب له أي رسالة). السبب: {ch.get('description', '')[:80]}")
            except httpx.HTTPError as e:
                line(False, "Telegram", f"ما قدرنا نتصل: {type(e).__name__}")

        # Discord (optional): a GET on a webhook returns its metadata without posting
        dw = env("DISCORD_WEBHOOK_URL")
        if dw:
            try:
                r = await c.get(dw)
                line(r.status_code == 200, "Discord", "الرابط شغّال" if r.status_code == 200 else f"الرابط مرفوض ({r.status_code})")
            except httpx.HTTPError as e:
                line(False, "Discord", f"ما قدرنا نتصل: {type(e).__name__}")

        # Solana RPC (optional)
        rpc = env("SOLANA_RPC_URL")
        if not rpc:
            line(None, "Solana RPC", "غير مضبوط (اختياري؛ RugCheck يكفي)")
        else:
            host = urlparse(rpc).hostname or "?"
            try:
                r = await c.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"})
                res = r.json() if r.status_code == 200 else {}
                line(res.get("result") == "ok", "Solana RPC", f"{host}: " + ("شغّال" if res.get("result") == "ok" else f"رد {r.status_code} {str(res)[:80]}"))
            except (httpx.HTTPError, ValueError) as e:
                line(False, "Solana RPC", f"{host}: ما قدرنا نتصل ({type(e).__name__})")

    # Dashboard token and database
    dt = env("DASHBOARD_TOKEN")
    if not dt:
        line(None, "DASHBOARD_TOKEN", "فاضي: محلياً عادي، لكن على Railway إلزامي (ولّده بـ: openssl rand -hex 24)")
    else:
        line(len(dt) >= 16, "DASHBOARD_TOKEN", "موجود" if len(dt) >= 16 else "قصير، خلّه 16 حرف أو أكثر")
    db = Database(team=cfg.get("team", "claude"))
    ok = await db.ping()
    line(ok, "قاعدة البيانات", ("Postgres" if not db.is_sqlite else "SQLite محلي (data/agents.db)") + (" شغّالة" if ok else " ما تشتغل"))
    await db.close()
    if cfg["mode"] != "paper":
        line(False, "الوضع", "mode لازم يكون paper")
    print("\n" + ("كل شيء جاهز ✅" if ok_all else "فيه شيء يحتاج تصليح ❌ (شوف فوق)"))
    return ok_all


async def report() -> None:
    cfg = load_config()
    db = Database(team=cfg.get("team", "claude"))
    await db.init()
    from .metrics import evaluate_test
    trades = await db.closed_positions(cfg["version"])
    spend = sum(v["usd"] for v in (await db.spend_by_service()).values())
    st = evaluate_test(trades, cfg, spend, None)
    print(json.dumps(jsonable({k: st[k] for k in ("verdict", "progress", "planned", "summary", "criteria",
                                                   "early_stop", "calibration")}), indent=2))
    await db.close()


async def check(mint: str) -> None:
    from .sources.dexscreener import DexScreener
    from .sources.safety import SafetyClient
    cfg = load_config()
    dex, saf = DexScreener(), SafetyClient(os.environ.get("SOLANA_RPC_URL") or None)
    try:
        snap = await dex.snapshot(mint)
        if not snap:
            print("no Solana pair found on DexScreener")
            return
        ok, reasons = market_filter(snap, cfg)
        rep = await saf.report(mint)
        safe, sreasons = safety_gate(rep, cfg)
        print(json.dumps(jsonable({
            "symbol": snap["symbol"], "dex": snap["dex"], "url": snap["url"],
            "market": {k: snap[k] for k in ("price_usd", "liquidity_usd", "vol_m5", "buys_m5", "sells_m5",
                                            "price_change_m5", "age_min")},
            "market_filter": {"pass": ok, "reasons": reasons},
            "safety": {k: (rep or {}).get(k) for k in ("mint_authority_revoked", "freeze_authority_revoked", "top10_pct",
                                                       "dev_pct", "bundle_pct", "lp_locked_pct", "holders", "rug_score")},
            "safety_gate": {"pass": safe, "reasons": sreasons, "minor_flags": minor_flags(rep, cfg)},
        }), indent=2))
    finally:
        await dex.aclose()
        await saf.aclose()


def main() -> None:
    load_dotenv()
    setup_logging()
    ap = argparse.ArgumentParser(prog="python -m app.main")
    ap.add_argument("command", nargs="?", default="run", choices=["run", "demo", "report", "check", "simulate", "doctor"])
    ap.add_argument("mint", nargs="?")
    ap.add_argument("--trades", type=int, default=100)
    ap.add_argument("--speed", type=float, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-minutes", type=float, default=45)
    a = ap.parse_args()
    if a.command == "report":
        asyncio.run(report())
    elif a.command == "doctor":
        sys.exit(0 if asyncio.run(doctor()) else 1)
    elif a.command == "simulate":
        asyncio.run(simulate(a.trades, a.speed, a.seed, a.max_minutes))
    elif a.command == "check":
        if not a.mint:
            ap.error("check needs a token mint address")
        asyncio.run(check(a.mint))
    else:
        asyncio.run(run(demo=a.command == "demo"))


if __name__ == "__main__":
    main()
