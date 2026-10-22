"""pump.fun launches & migrations via the PumpPortal Data API WebSocket (blueprint 12.2)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

log = logging.getLogger("pumpportal")
URI = "wss://pumpportal.fun/api/data"

Event = dict
OnEvent = Callable[[Event], Awaitable[None]]


def parse_event(d: dict) -> Event | None:
    mint = d.get("mint")
    if not mint or not isinstance(mint, str):
        return None
    tx = d.get("txType") or ""
    kind = "migrate" if tx == "migrate" else "create"
    return {
        "mint": mint,
        "symbol": d.get("symbol"),
        "name": d.get("name"),
        "creator": d.get("traderPublicKey") if kind == "create" else None,
        "event": kind,
        "market_cap_sol": d.get("marketCapSol"),
    }


class PumpPortalStream:
    def __init__(self, on_event: OnEvent, uri: str = URI):
        self.on_event = on_event
        self.uri = uri
        self.last_message_at = 0.0
        self.connected = False
        self.reconnects = 0

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.uri, ping_interval=20, ping_timeout=20, max_size=2**20) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))
                    self.connected = True
                    backoff = 1
                    log.info("connected to PumpPortal")
                    async for raw in ws:
                        self.last_message_at = time.time()
                        try:
                            d = json.loads(raw)
                        except ValueError:
                            continue
                        ev = parse_event(d) if isinstance(d, dict) else None
                        if ev:
                            await self.on_event(ev)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("PumpPortal stream error: %s (reconnect in %ss)", e, backoff)
            self.connected = False
            self.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    def stale_seconds(self) -> float:
        return time.time() - self.last_message_at if self.last_message_at else float("inf")
