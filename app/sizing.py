"""Confidence Score -> position size (blueprint 10.2)."""
from __future__ import annotations


def composite_score(votes: dict, weights: dict, penalties: int = 0, penalty_points: int = 10) -> int:
    s = sum(votes[a]["score"] * w for a, w in weights.items())
    return max(0, min(100, round(s - penalty_points * penalties)))


def size_for(score: int, cfg: dict) -> float:
    sz = cfg["sizing"]
    m = sz["size_multiplier"]
    if score < sz["min_confidence_to_trade"]:
        return 0.0
    if score <= 85:
        mult = m["at_70"] + (score - 70) / 15 * (m["at_85"] - m["at_70"])
    else:
        mult = m["at_85"] + (score - 85) / 15 * (m["at_100"] - m["at_85"])
    return round(min(sz["base_size_sol"] * max(mult, 0.0), sz["max_size_sol"]), 6)
