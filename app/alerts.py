"""Telegram / Discord notifications (blueprint 14.3). Failures are logged, never raised."""
from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger("alerts")


class Alerter:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
        self.discord = os.environ.get("DISCORD_WEBHOOK_URL")
        self.c = client or httpx.AsyncClient(timeout=10)
        self._last: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool((self.tg_token and self.tg_chat) or self.discord)

    async def send(self, text: str, dedupe_key: str | None = None, min_interval_s: int = 0) -> None:
        if dedupe_key:
            t = self._last.get(dedupe_key, 0)
            if time.time() - t < min_interval_s:
                return
            self._last[dedupe_key] = time.time()
        log.info("ALERT %s", text)
        if not self.enabled:
            return
        try:
            if self.tg_token and self.tg_chat:
                await self.c.post(f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                                  json={"chat_id": self.tg_chat, "text": text[:4000], "disable_web_page_preview": True})
            if self.discord:
                await self.c.post(self.discord, json={"content": text[:1900]})
        except Exception as e:
            log.warning("alert delivery failed: %s", e)

    async def aclose(self) -> None:
        await self.c.aclose()
