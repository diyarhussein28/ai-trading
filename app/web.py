"""FastAPI dashboard + /health (blueprint 5.3, 14)."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

STATIC = Path(__file__).parent / "static"


def create_app(engine_ref: dict) -> FastAPI:
    """engine_ref['engine'] is filled in once the engine has started."""
    app = FastAPI(title="Memecoin Agents", docs_url=None, redoc_url=None)
    token = os.environ.get("DASHBOARD_TOKEN", "").strip()

    def authorize(request: Request) -> None:
        if not token:
            return
        supplied = request.query_params.get("token") or request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    async def health():
        eng = engine_ref.get("engine")
        if eng is None:
            return JSONResponse({"ok": False, "status": "starting"}, status_code=503)
        ok, checks = eng.healthy()
        db_ok = await eng.db.ping()
        ok = ok and db_ok
        return JSONResponse({"ok": ok, "db": db_ok, **checks}, status_code=200 if ok else 503)

    @app.get("/api/state")
    async def state(request: Request):
        authorize(request)
        eng = engine_ref.get("engine")
        if eng is None:
            raise HTTPException(status_code=503, detail="starting")
        return await eng.state()

    @app.post("/api/pause")
    async def pause(request: Request):
        authorize(request)
        if not token:
            raise HTTPException(status_code=403, detail="set DASHBOARD_TOKEN to enable controls")
        eng = engine_ref["engine"]
        paused = not await eng.db.meta_get("paused", False)
        await eng.db.meta_set("paused", paused)
        await eng.alerts.send("⏸️ تم إيقاف الصفقات الجديدة يدوياً" if paused else "▶️ رجعت الصفقات الجديدة")
        return {"paused": paused}

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    return app
