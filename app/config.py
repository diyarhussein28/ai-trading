"""Configuration loading: YAML file + environment, with a stable hash so a frozen test can detect drift."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

REQUIRED_SECTIONS = (
    "version", "mode", "sizing", "risk", "discovery", "filters", "safety",
    "consensus", "exits", "costs", "social", "agents", "lessons", "test", "runtime",
)


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    """Minimal .env reader (no dependency). Existing environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def config_hash(cfg: dict) -> str:
    """Hash of everything that affects trading decisions (runtime-only keys excluded)."""
    relevant = {k: v for k, v in cfg.items() if k not in ("runtime", "llm_pricing_usd_per_mtok", "_meta")}
    blob = json.dumps(relevant, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def validate(cfg: dict) -> None:
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ValueError(f"config is missing sections: {missing}")
    if cfg["mode"] not in ("paper", "live"):
        raise ValueError("mode must be 'paper' or 'live'")
    w = cfg["consensus"]["weights"]
    if set(w) != {"professor", "sniper", "detective"} or abs(sum(w.values()) - 1.0) > 1e-6:
        raise ValueError("consensus.weights must cover professor/sniper/detective and sum to 1.0")
    s = cfg["sizing"]
    if not (0 < s["base_size_sol"] <= s["max_size_sol"]):
        raise ValueError("sizing: need 0 < base_size_sol <= max_size_sol")
    if not (0 <= s["min_confidence_to_trade"] <= 100):
        raise ValueError("sizing.min_confidence_to_trade must be 0-100")
    if cfg["exits"]["stop_loss_pct"] >= 0 or cfg["exits"]["take_profit_pct"] <= 0:
        raise ValueError("exits: stop_loss_pct must be < 0 and take_profit_pct > 0")
    if cfg["social"]["on_missing"] not in ("pass", "degrade"):
        raise ValueError("social.on_missing must be 'pass' or 'degrade'")
    if cfg["agents"]["backend"] not in ("llm", "rules"):
        raise ValueError("agents.backend must be 'llm' or 'rules'")
    n = cfg["social"]["max_posts_per_token"]
    if not (10 <= n <= 100):
        raise ValueError("social.max_posts_per_token must be 10-100 (X API limit)")


def load_config(path: str | os.PathLike | None = None, overrides: dict | None = None) -> dict[str, Any]:
    path = path or os.environ.get("CONFIG_PATH", "config/v7.yaml")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    validate(cfg)
    cfg.setdefault("team", "claude")
    cfg["_meta"] = {"path": str(path), "hash": config_hash(cfg)}
    return cfg


# Overrides for `python -m app.main demo`: synthetic market, rule-based agents, fast clock.
DEMO_OVERRIDES: dict[str, Any] = {
    "version": "V7-demo",
    "agents": {"backend": "rules"},
    "social": {"on_missing": "pass"},
    "discovery": {"scan_interval_seconds": 1, "new_token_first_check_minutes": 0.05,
                  "recheck_schedule_minutes": [0.05, 0.15, 0.3, 0.6, 1, 2],
                  "migration_recheck_seconds": 3, "reevaluate_minutes": 1, "profiles_poll_seconds": 5},
    "filters": {"min_age_minutes": 0.05},
    "safety": {"recheck_blocked_minutes": 1},
    "exits": {"time_stop_minutes": 2},
    "risk": {"cooldown_minutes_after_exit": 2, "kill_switch_pause_hours": 0.02},
    "lessons": {"post_mortem": False},
    "runtime": {"price_poll_seconds": 1},
}
