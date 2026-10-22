import os

import pytest
import pytest_asyncio

from app.config import load_config
from app.db import Database, md


@pytest.fixture
def cfg():
    return load_config("config/v7.yaml")


@pytest.fixture
def rules_cfg():
    return load_config("config/v7.yaml", overrides={"agents": {"backend": "rules"}, "social": {"on_missing": "degrade"},
                                                     "lessons": {"post_mortem": False}})


@pytest_asyncio.fixture
async def db(tmp_path):
    """SQLite by default; set TEST_DATABASE_URL=postgresql+asyncpg://... to run the suite on Postgres."""
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/t.db"
    d = Database(url)
    if not d.is_sqlite:
        async with d.engine.begin() as c:
            await c.run_sync(md.drop_all)
    await d.init()
    yield d
    await d.close()


def snap(**kw):
    base = {
        "mint": "MintAAA", "symbol": "AAA", "name": "Aaa", "ts": 0, "dex": "pumpswap", "pair": "P", "url": None,
        "price_usd": 0.001, "price_native": 0.001 / 150, "sol_usd": 150.0, "liquidity_usd": 30_000.0,
        "vol_m5": 20_000.0, "vol_h1": 80_000.0, "buys_m5": 300, "sells_m5": 150, "buys_h1": 900, "sells_h1": 600,
        "price_change_m5": 20.0, "price_change_h1": 60.0, "fdv": 1e6, "market_cap": 1e6, "age_min": 25.0,
        "socials": [{"type": "twitter", "url": "https://x.com/a"}, {"type": "telegram", "url": "https://t.me/a"}],
        "websites": [{"url": "https://a.xyz"}], "boosts": 0,
    }
    base.update(kw)
    return base


def safety_rep(**kw):
    base = {
        "source": "test", "mint_authority_revoked": True, "freeze_authority_revoked": True, "top10_pct": 15.0,
        "dev_pct": 1.0, "bundle_pct": 2.0, "insider_networks": 0, "lp_locked_pct": 100.0,
        "lp_status": "burned_or_locked", "holders": 800, "rug_score": 10.0, "rugged": False,
        "mutable_metadata": False, "transfer_fee_pct": 0.0, "risks": [], "quote_liquidity_usd": 15_000.0,
    }
    base.update(kw)
    return base
