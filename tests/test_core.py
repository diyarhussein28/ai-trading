"""Pure-logic tests: sizing, filters, safety parsing, exits, metrics, social features, watchlist, LLM output guard."""
import time

import pytest

from app.agents.llm import normalize_vote
from app.filters import market_filter, minor_flags, safety_gate
from app.metrics import calibration, evaluate_test, max_drawdown, summary, wilson
from app.paper_broker import LiveTradingNotImplemented, assert_paper_mode, entry_fill, evaluate_exit, exit_fill
from app.sizing import composite_score, size_for
from app.sources.safety import parse_rugcheck
from app.sources.social import parse_search, summarize
from app.watchlist import Watchlist

from .conftest import safety_rep, snap


# ---------------------------------------------------------------- sizing (blueprint 10.2)
def test_composite_score_weights_and_penalty(cfg):
    w = cfg["consensus"]["weights"]
    votes = {"professor": {"score": 90}, "sniper": {"score": 80}, "detective": {"score": 70}}
    assert composite_score(votes, w) == round(90 * .45 + 80 * .30 + 70 * .25)  # 82
    assert composite_score(votes, w, penalties=2) == 62


@pytest.mark.parametrize("score,expected", [(69, 0.0), (70, 0.01025), (85, 0.0205), (100, 0.03075)])
def test_size_for_linear_map(cfg, score, expected):
    assert size_for(score, cfg) == pytest.approx(expected, rel=1e-6)


def test_size_capped(cfg):
    cfg["sizing"]["max_size_sol"] = 0.025
    assert size_for(100, cfg) == 0.025


# ---------------------------------------------------------------- filters & safety
def test_market_filter_pass_and_reasons(cfg):
    assert market_filter(snap(), cfg) == (True, [])
    ok, r = market_filter(snap(liquidity_usd=5_000, vol_m5=100, buys_m5=10, sells_m5=20, price_change_m5=200,
                               age_min=1), cfg)
    assert not ok and len(r) == 5


def test_safety_gate_blocks_on_missing_data(cfg):
    assert safety_gate(None, cfg) == (False, ["BLOCK: safety data unavailable"])


def test_safety_gate_rules(cfg):
    assert safety_gate(safety_rep(), cfg) == (True, [])
    ok, r = safety_gate(safety_rep(mint_authority_revoked=False, top10_pct=50, dev_pct=9, bundle_pct=30,
                                   lp_locked_pct=10, quote_liquidity_usd=200,
                                   risks=[{"name": "Low Liquidity", "level": "danger"}]), cfg)
    assert not ok
    joined = " ".join(r)
    for needle in ("mint authority", "top10", "dev holds", "bundled", "LP not locked", "SOL", "Low Liquidity"):
        assert needle in joined


def test_minor_flags(cfg):
    assert minor_flags(safety_rep(), cfg) == []
    f = minor_flags(safety_rep(top10_pct=27, mutable_metadata=True,
                               risks=[{"name": "Single holder ownership", "level": "warn"}]), cfg)
    assert len(f) == 3


RUGCHECK_SAMPLE = {
    "mintAuthority": None, "freezeAuthority": None, "creator": "CREATOR", "creatorBalance": 0,
    "token": {"supply": 1_000_000, "mintAuthority": None, "freezeAuthority": None},
    "tokenMeta": {"mutable": False}, "totalHolders": 1339, "score_normalised": 36, "rugged": False,
    "risks": [{"name": "Single holder ownership", "level": "warn", "value": "35%"}],
    "knownAccounts": {"POOL": {"type": "AMM"}, "CREATOR": {"type": "CREATOR"}},
    "markets": [{"pubkey": "POOL", "liquidityA": "POOLVAULT_A", "liquidityB": "POOLVAULT_B",
                 "lp": {"lpLockedPct": 100, "quoteUSD": 17595.0}}],
    "topHolders": [
        {"address": "H1", "owner": "CREATOR", "pct": 35.6, "insider": False},
        {"address": "POOLVAULT_A", "owner": "POOL", "pct": 10.4, "insider": False},
        {"address": "H3", "owner": "W3", "pct": 7.2, "insider": True},
        {"address": "H4", "owner": "W4", "pct": 2.0, "insider": False},
    ],
}


def test_parse_rugcheck_excludes_pool_and_finds_dev():
    rep = parse_rugcheck(RUGCHECK_SAMPLE)
    assert rep["mint_authority_revoked"] and rep["freeze_authority_revoked"]
    assert rep["top10_pct"] == pytest.approx(35.6 + 7.2 + 2.0)  # pool vault excluded
    assert rep["dev_pct"] == pytest.approx(35.6)  # creator-owned holder counted even though creatorBalance=0
    assert rep["bundle_pct"] == pytest.approx(7.2)
    assert rep["lp_status"] == "burned_or_locked" and rep["quote_liquidity_usd"] == 17595.0


# ---------------------------------------------------------------- exits (blueprint 6.3, 12.6)
def _pos(cfg, **kw):
    mid = 1.0
    p = {"id": 1, "size_sol": 0.0205, "opened_at": time.time(), "entry_mid_price": mid,
         "entry_price": entry_fill(cfg, mid, 0.0205, 150, 30_000), "entry_liq": 30_000.0, "last_price": mid,
         "last_liq": 30_000.0, "missing_polls": 0, "peak_return_pct": 0.0}
    p.update(kw)
    return p


def test_fill_costs_round_trip(cfg):
    e = entry_fill(cfg, 1.0, 0.0205, 150, 30_000)
    x = exit_fill(cfg, 1.0, 0.0205, 150, 30_000)
    assert 1.03 < e < 1.031 and 0.969 < x < 0.97  # 3% per side + tiny impact


@pytest.mark.parametrize("price,reason", [(1.5, "TP"), (0.75, "SL")])
def test_tp_sl(cfg, price, reason):
    sig, _ = evaluate_exit(_pos(cfg), snap(price_usd=price, liquidity_usd=30_000), cfg, time.time(), 150)
    assert sig and sig.reason == reason


def test_trailing_stop(cfg):
    p = _pos(cfg, peak_return_pct=30.0)
    sig, _ = evaluate_exit(p, snap(price_usd=1.18, liquidity_usd=30_000), cfg, time.time(), 150)
    assert sig and sig.reason == "TRAIL"  # ~ +10.5% net, more than 12 below the +30 peak


def test_time_stop(cfg):
    p = _pos(cfg, opened_at=time.time() - 11 * 60)
    sig, _ = evaluate_exit(p, snap(price_usd=1.05, liquidity_usd=30_000), cfg, time.time(), 150)
    assert sig and sig.reason == "TIME"


def test_rug_on_liquidity_drop(cfg):
    sig, _ = evaluate_exit(_pos(cfg), snap(price_usd=0.9, liquidity_usd=10_000), cfg, time.time(), 150)
    assert sig and sig.reason == "RUG" and sig.price < 0.9 * 0.91


def test_missing_data_counts_then_exits(cfg):
    p = _pos(cfg)
    for i in range(cfg["exits"]["missing_data_polls_before_rug_exit"] - 1):
        sig, upd = evaluate_exit(p, None, cfg, time.time(), 150)
        assert sig is None
        p["missing_polls"] = upd["missing_polls"]
    sig, _ = evaluate_exit(p, None, cfg, time.time(), 150)
    assert sig.reason == "RUG" and sig.price < 0.5


def test_hold_when_nothing_fires(cfg):
    sig, upd = evaluate_exit(_pos(cfg), snap(price_usd=1.1, liquidity_usd=30_000), cfg, time.time(), 150)
    assert sig is None and upd["peak_return_pct"] > 0


def test_live_mode_refused(cfg, monkeypatch):
    cfg["mode"] = "live"
    monkeypatch.setenv("ALLOW_LIVE", "yes")
    with pytest.raises(LiveTradingNotImplemented):
        assert_paper_mode(cfg)


# ---------------------------------------------------------------- metrics (blueprint 6.2, 16)
V7_VIDEO = [42.38, -1.00, 40.73, 42.77, 4.25, 25.29, -51.17, 44.43, 40.67, 42.60]


def _trades(returns, conf=80):
    now = int(time.time())
    return [{"return_pct": r, "pnl_sol": 0.0205 * r / 100, "confidence": conf, "exit_reason": "TP" if r > 40 else "X",
             "peak_return_pct": r, "opened_at": now - 300, "closed_at": now} for r in returns]


def test_wilson_matches_blueprint():
    lo, hi = wilson(8, 10)
    assert round(lo, 2) == 0.49 and round(hi, 2) == 0.94
    lo, hi = wilson(80, 100)
    assert round(lo, 2) == 0.71 and round(hi, 2) == 0.87


def test_summary_matches_blueprint_numbers():
    s = summary(_trades(V7_VIDEO))
    assert s["hit"] == 0.8
    assert s["avg_return_pct"] == pytest.approx(23.1, abs=0.05)
    assert s["avg_win_pct"] == pytest.approx(35.4, abs=0.05)
    assert s["avg_loss_pct"] == pytest.approx(-26.1, abs=0.05)
    assert s["profit_factor"] == pytest.approx(5.4, abs=0.1)


def test_max_drawdown():
    assert max_drawdown([1, -2, 1, -3, 5]) == 4


def test_evaluate_test_in_progress_and_early_stop(cfg):
    st = evaluate_test(_trades(V7_VIDEO), cfg, 1.0, 150)
    assert st["verdict"] == "IN PROGRESS" and st["progress"] == 10
    bad = _trades([-22] * 30 + [5] * 12)
    st = evaluate_test(bad, cfg, 0.0, 150)
    assert st["verdict"] == "STOPPED EARLY" and st["early_stop"]


def test_calibration_buckets(cfg):
    trades = _trades([45, 45, 45], conf=90) + _trades([-20, 5, -20], conf=72)
    cal = calibration(trades, 40)
    assert cal["90-100"]["n"] == 3 and cal["70-79"]["n"] == 3
    assert cal["90-100"]["avg_return_pct"] > cal["70-79"]["avg_return_pct"]
    assert 0 <= cal["brier_tp"] <= 1


# ---------------------------------------------------------------- social features
def test_parse_and_summarize_social():
    payload = {
        "data": [{"id": str(i), "author_id": str(i % 6), "text": f"post {i % 4}", "created_at": "2026-10-22T10:00:00Z",
                  "public_metrics": {"like_count": 3}} for i in range(12)],
        "includes": {"users": [{"id": str(u), "username": f"u{u}", "created_at": "2020-01-01T00:00:00Z",
                                "public_metrics": {"followers_count": 50_000 if u == 0 else 100}} for u in range(6)]},
    }
    posts = parse_search(payload)
    assert len(posts) == 12 and posts[0]["followers"] == 50_000
    s = summarize(posts, 10_000, 30)
    assert s["distinct_authors"] == 6 and s["aged_author_share"] == 1.0
    assert s["duplicate_text_share"] == pytest.approx(8 / 12, abs=0.01)
    assert summarize(None, 10_000, 30) == {"available": False, "posts": 0}


# ---------------------------------------------------------------- watchlist
def test_watchlist_schedule_and_promotion(cfg):
    w = Watchlist(cfg)
    t0 = 1_000_000.0
    assert w.add("m1", "A", "create", now=t0)
    assert w.due(10, now=t0) == []  # first check after 3 minutes
    assert [e.mint for e in w.due(10, now=t0 + 181)] == ["m1"]
    w.add("m1", "A", "migrate", now=t0 + 200)  # migration promotes it to hot, due now
    assert w.entries["m1"].hot and [e.mint for e in w.due(10, now=t0 + 200)] == ["m1"]
    w.checked("m1", snap(mint="m1", age_min=500), now=t0 + 201)  # too old -> dropped
    assert "m1" not in w.entries


# ---------------------------------------------------------------- LLM output guard
@pytest.mark.parametrize("raw,vote,score", [
    ({"vote": "buy", "score": 150, "reason": "x", "red_flags": []}, "BUY", 100),
    ({"vote": "HODL", "score": 50}, "PASS", 0),
    ({"score": "abc"}, "PASS", 0),
])
def test_normalize_vote(raw, vote, score):
    v = normalize_vote(raw)
    assert v["vote"] == vote and v["score"] == score


def test_verdict_inconclusive_when_a_condition_lacks_data(cfg):
    # 100 strong trades all scored 85: the 70-79 calibration bucket is empty, so it cannot be judged
    trades = _trades(([45] * 7 + [-10] * 3) * 10, conf=85)
    st = evaluate_test(trades, cfg, 0.0, 150)
    assert "fail" not in {c["status"] for c in st["criteria"]}
    assert st["verdict"] == "INCONCLUSIVE"
    trades = _trades([-30] * 60 + [45] * 40, conf=85)
    assert evaluate_test(trades, cfg, 0.0, 150)["verdict"] in ("FAILED", "STOPPED EARLY")
