"""FastAPI hub.

Serves the stage page (captured by TikTok LIVE Studio) and the operator console,
and relays JSON messages between controllers and the stage:

  /ws/stage    the stage page connects here; receives commands, sends events (ready, replay_done)
  /ws/control  controllers (the director, dry-run scripts, the console) connect here;
               anything they send is forwarded to the stage, and stage events are
               forwarded back to every controller.

Run:  uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("hub")
ROOT = Path(__file__).resolve().parent
STAGE_STATIC = ROOT / "stage" / "static"
CONSOLE_STATIC = ROOT / "console" / "static"

app = FastAPI(title="Talking Trading Guy hub")


@app.middleware("http")
async def no_cache(request, call_next):
    """Stage assets change during development; never let Chrome cache them."""
    response = await call_next(request)
    if request.url.path.startswith(("/stage", "/console")):
        response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/stage/static", StaticFiles(directory=STAGE_STATIC), name="stage-static")
app.mount("/console/static", StaticFiles(directory=CONSOLE_STATIC), name="console-static")


class Hub:
    def __init__(self) -> None:
        self.stages: set[WebSocket] = set()
        self.controllers: set[WebSocket] = set()
        self.last_state: dict[str, dict] = {}  # last message per "sticky" type, replayed to a reconnecting stage

    async def _send_all(self, sockets: set[WebSocket], text: str) -> None:
        dead = []
        for ws in list(sockets):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    async def to_stage(self, msg: dict) -> None:
        t = msg.get("type")
        if t in {"lesson", "mode", "ticker", "question", "disclosure", "state"}:
            self.last_state[t] = msg
        elif t == "kline" and "candles" in msg:          # history seed for a room screen
            self.last_state[f"kline:{msg.get('symbol')}"] = msg
        elif t == "kline" and "candle" in msg:           # keep the seed current with live candles
            seed = self.last_state.get(f"kline:{msg.get('symbol')}")
            if seed:
                arr = seed["candles"]
                if arr and arr[-1]["time"] == msg["candle"]["time"]:
                    arr[-1] = msg["candle"]
                else:
                    arr.append(msg["candle"])
                    del arr[:-150]
        elif t == "quote":
            self.last_state[f"quote:{msg.get('symbol')}"] = msg
        elif t == "chart" and msg.get("action") == "load":   # a stage that connects mid-lesson gets the current chart
            self.last_state["chart:load"] = {**msg, "replay": False}
            for k in [k for k in self.last_state if k.startswith("chart:draw")]:
                del self.last_state[k]
        elif t == "chart" and msg.get("action") in {"marker", "hline", "trendline", "zone", "rect", "fib", "path", "arrow", "note", "indicator", "highlight"}:
            self.last_state[f"chart:draw:{len(self.last_state)}:{time.time()}"] = msg   # drawings since the load
        elif t == "chart" and msg.get("action") == "clear":
            for k in [k for k in self.last_state if k.startswith("chart:draw")]:
                del self.last_state[k]
        await self._send_all(self.stages, json.dumps(msg))

    async def to_controllers(self, msg: dict) -> None:
        await self._send_all(self.controllers, json.dumps(msg))


hub = Hub()


@app.get("/")
async def root():
    return RedirectResponse("/stage")


@app.get("/stage")
async def stage_page():
    return FileResponse(STAGE_STATIC / "index.html")


@app.get("/console")
async def console_page():
    return FileResponse(CONSOLE_STATIC / "console.html")


@app.get("/progress")
async def progress_page():
    return FileResponse(CONSOLE_STATIC / "progress.html")


@app.get("/progress.json")
async def progress_json():
    import asyncio

    from .progress import collect

    return await asyncio.to_thread(collect)


@app.get("/health")
async def health():
    return {"ok": True, "stages": len(hub.stages), "controllers": len(hub.controllers)}


@app.websocket("/ws/stage")
async def ws_stage(ws: WebSocket):
    await ws.accept()
    hub.stages.add(ws)
    log.info("stage connected (%d)", len(hub.stages))
    try:
        # replay order: sticky UI state, then the current chart, then its drawings
        keys = sorted(hub.last_state.keys(), key=lambda k: (0 if not k.startswith("chart") else 1 if k == "chart:load" else 2, k))
        for k in keys:
            await ws.send_text(json.dumps(hub.last_state[k]))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg["from"] = "stage"
            if msg.get("type") == "ready":
                log.info("stage ready: %sx%s css px, dpr %s (%s)", msg.get("w"), msg.get("h"), msg.get("dpr"), msg.get("ua", ""))
            if msg.get("type") == "stage_error":
                log.warning("stage error: %s | %s", msg.get("text", "")[:400], msg.get("ctx", ""))
                continue
            await hub.to_controllers(msg)
    except WebSocketDisconnect:
        pass
    finally:
        hub.stages.discard(ws)
        log.info("stage disconnected (%d)", len(hub.stages))


@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await ws.accept()
    hub.controllers.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue
            if msg.get("type") in {"operator", "status"}:
                # operator commands and director status go to the other controllers (director/console), not the stage
                text = json.dumps(msg)
                for other in list(hub.controllers):
                    if other is not ws:
                        try:
                            await other.send_text(text)
                        except Exception:
                            hub.controllers.discard(other)
                continue
            await hub.to_stage(msg)
            if msg.get("type") == "state":
                # the director's state (paused, muted, music mode, now playing) also drives the console's buttons
                text = json.dumps(msg)
                for other in list(hub.controllers):
                    if other is not ws:
                        try:
                            await other.send_text(text)
                        except Exception:
                            hub.controllers.discard(other)
    except WebSocketDisconnect:
        pass
    finally:
        hub.controllers.discard(ws)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
