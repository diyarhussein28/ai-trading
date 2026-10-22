# Memecoin Agents — V7 (paper trading)

A working build of the system in [ai-trading-agents-video-blueprint.md](ai-trading-agents-video-blueprint.md):
three AI agents (THE DETECTIVE, THE SNIPER, THE PROFESSOR) that hunt Solana memecoins and only enter on
**unanimous consensus**. The Professor holds a **veto**, and a **Confidence Score** sets the position size. Every
trade is **paper**, sized in SOL, and measured by the 100-trade test protocol.

> ⚠️ Not financial advice. Memecoins are among the riskiest assets that exist, and most go to zero. Live trading is
> deliberately not implemented. Section 17 of the blueprint says to pass the 100-trade paper test first.

**دليل التشغيل الكامل بالعربي: [docs/SETUP_AR.md](docs/SETUP_AR.md)**

## How a coin becomes a trade

```
pump.fun launches & migrations (PumpPortal WS) + DexScreener profiles/boosts
        │  watchlist re-checks each token on a backoff schedule (bonding-curve coins mature for minutes)
        ▼
HARD FILTER (code)   liquidity ≥ $10k · 5m vol ≥ $5k · buys/sells ≥ 1.2 · age 3–180m · not parabolic
        ▼
SAFETY GATE (code)   mint & freeze revoked · top-10 ≤ 30% (pools excluded) · dev ≤ 5% · insiders ≤ 20%
                     LP locked · ≥ $5k real SOL in the pool · no RugCheck "danger" · any API error = BLOCK
        ▼
SOCIAL (official X API, only for survivors, 25 posts, 10-min cache, hourly/daily $ caps)
        ▼
🕵️ DETECTIVE + 🎯 SNIPER vote in parallel ──► 🧪 PROFESSOR (sees their votes, final call, veto)
        ▼
3/3 BUY  →  composite score (0.45 P · 0.30 S · 0.25 D − 10/minor flag)  →  ≥ 70 trades, size 0.5×–1.5× of 0.0205 SOL
        ▼
fresh price re-check → PAPER BROKER: fees + slippage + price impact · TP +40% · SL −22% · trail 12% after +20%
                       · 10-min time stop · rug exit on −50% liquidity or vanished pair
        ▼
journal · blackboard · post-mortem lessons · checkpoint report every 10 trades · 100-trade verdict
```

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

Try the whole pipeline offline, with a synthetic market, rule-based agents and no keys:

```bash
.venv/bin/python -m app.main demo
```

Open http://localhost:8080. Demo numbers are made up and say nothing about real performance.

To run against the real market (paper), copy `.env.example` to `.env`, fill in `ANTHROPIC_API_KEY` (and ideally `X_BEARER_TOKEN`), then:

```bash
.venv/bin/python -m app.main run
```

Check one real token against the filter and the safety gate:

```bash
.venv/bin/python -m app.main check <MINT_ADDRESS>
```

Run the whole 100-trade protocol on the synthetic market with a 30× clock (~10 min, no keys):

```bash
.venv/bin/python -m app.main simulate --trades 100 --speed 30
```

Print the 100-trade test status:

```bash
.venv/bin/python -m app.main report
```

Run the tests (SQLite by default; set `TEST_DATABASE_URL=postgresql+asyncpg://...` to run them on Postgres):

```bash
.venv/bin/python -m pytest
```

### Important: X data decides whether it trades at all
The blueprint's rule is that the Detective and Sniper vote **PASS** without social data (`social.on_missing: pass`).
So with no `X_BEARER_TOKEN`, **no trades will open**, and the dashboard warns you about this. Your options:
- add an official X API v2 bearer token, and set `social.est_usd_per_post` to your plan's real price so the budget guard is accurate, or
- set `social.on_missing: degrade`. The X agents then judge only from the DexScreener profile (real X/Telegram/website links, freshness), and their score is capped at 75.

Browser-cookie scraping of X (what the video did) is **not** included. It breaks X's terms, gets accounts banned,
and a ban mid-test corrupts the 100-trade statistics.

## Configuration
Everything that affects decisions lives in [config/v7.yaml](config/v7.yaml). The engine stores a hash of it per
`version`. If you change the config without bumping `version`, the dashboard shows a red "changed mid-test"
banner. **One change per version**, with a fixed trade count (blueprint 15).

| Setting | Default | Where it comes from |
|---|---|---|
| `agents.backend` | `llm` | Claude votes; `rules` = deterministic agents (no key) |
| `CLAUDE_VOTE_MODEL` | `claude-haiku-5-5` | fast voter (blueprint 9.1) |
| `CLAUDE_REVIEW_MODEL` | `claude-opus-5-5` | post-mortem lessons, with server-side refusal fallback |
| `lessons.inject` | `false` | blueprint 16.1: lessons are recorded, not injected, during the test |
| `sizing.base_size_sol` | `0.0205` | seen in the video |
| `exits.*` | TP 40 / SL −22 / trail 20→12 / 10 min | inferred from the V7 trade log (blueprint 6.3) |

## Deploy 24/7 on Railway (blueprint 14)
1. Push this repo, create a Railway project from it, and add the **Postgres** plugin (`DATABASE_URL` is injected).
2. Add Variables: `ANTHROPIC_API_KEY`, `X_BEARER_TOKEN`, optionally `SOLANA_RPC_URL`, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` or `DISCORD_WEBHOOK_URL`, and `DASHBOARD_TOKEN` (the dashboard is otherwise public).
3. `railway.json` pins **1 replica**, the `/health` check and restart-on-failure. A Postgres advisory lock makes a second instance exit instead of doubling every bet (the V1/V7 duplicate-trade bug).
4. Open positions live in the database and resume after a restart.

## The 100-trade test (blueprint 16)
The dashboard and `report` evaluate every success condition: Wilson 95% lower bound above the break-even hit rate,
profit factor ≥ 1.5 after costs, max drawdown ≤ 25% of paper capital, no single trade above 30% of profit, score
80+ beating 70–79 (calibration), and operating costs (LLM + X + hosting) below the paper profit. A report is
written every 10 trades. Entries stop automatically if PF < 0.8 after 40 trades or drawdown > 35%.

## Layout
```
app/
  main.py            CLI: run · demo · simulate · report · check
  engine.py          orchestrator (discovery → filter → safety → social → agents → broker → metrics)
  watchlist.py       re-check scheduling for maturing launches
  filters.py         hard filter, safety gate, minor flags
  consensus.py       3/3 + veto + composite score + sizing
  sizing.py          confidence → SOL size
  paper_broker.py    fills, exits, live-mode guard
  risk.py            open cap, daily loss, cooldown, kill switch, early-stop halt
  metrics.py         Wilson CI, PF, drawdown, calibration, test verdict, version table
  db.py              SQLite locally / Postgres on Railway, singleton lock
  web.py, static/    FastAPI dashboard + /health
  agents/            prompts, Claude client (structured JSON votes), rule agents, team
  sources/           PumpPortal, DexScreener, RugCheck(+RPC), X API, spend guard, demo market
config/v7.yaml       frozen test configuration
tests/               50 tests (logic + integration, no network; pass on SQLite and Postgres)
docs/SETUP_AR.md     step-by-step setup & operations guide (Arabic)
```
