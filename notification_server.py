"""
notification_server.py
======================
Custom push-notification server for the Wildlife Detection System.
Replaces ntfy.sh with a self-hosted WebSocket broadcast server.

Run this BEFORE starting main.py:
    python notification_server.py

Then open the web app on any device on the same Wi-Fi:
    http://<your-PC-IP>:8765/app

API:
  POST /alert          — wildlife detection system sends alerts here
  GET  /ws             — WebSocket stream for the PWA app
  GET  /app            — serves the PWA (mobile / desktop)
  GET  /status         — JSON health check
  GET  /history        — last 50 alerts as JSON
"""

import asyncio
import json
import logging
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

# ── Dependency check ─────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("[ERROR] Missing dependencies.  Run:")
    print("        pip install fastapi uvicorn")
    raise SystemExit(1)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("Hazard-notify")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Hazard Alert Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State ─────────────────────────────────────────────────────────────────────

_connected_clients: Set[WebSocket] = set()
_alert_history: deque = deque(maxlen=50)   # last 50 alerts
_server_start_time = time.time()


# ── WebSocket manager ─────────────────────────────────────────────────────────

async def _broadcast(message: dict):
    """Send a JSON message to every connected client."""
    dead = set()
    payload = json.dumps(message)
    for ws in list(_connected_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _connected_clients.difference_update(dead)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/status")
async def status():
    return JSONResponse({
        "status": "running",
        "uptime_seconds": round(time.time() - _server_start_time),
        "connected_clients": len(_connected_clients),
        "alerts_sent": len(_alert_history),
    })


@app.get("/history")
async def history():
    return JSONResponse(list(_alert_history))


@app.post("/alert")
async def receive_alert(request: Request):
    """
    Receive an alert from the detection system and broadcast to all clients.

    Expected JSON body:
    {
        "risk_level": "HIGH" | "MEDIUM" | "LOW",
        "title": "...",
        "message": "...",
        "priority": "urgent" | "high" | "default",
        "tags": "warning,red_circle",
        "animal": "venomous_snake",
        "category": "animal"
    }
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    required = {"risk_level", "title", "message"}
    if not required.issubset(data.keys()):
        raise HTTPException(status_code=422,
                            detail=f"Missing fields: {required - data.keys()}")

    alert = {
        "type": "alert",
        "risk_level": data.get("risk_level", "LOW"),
        "title": data.get("title", "Hazard Alert"),
        "message": data.get("message", ""),
        "priority": data.get("priority", "default"),
        "tags": data.get("tags", "eyes"),
        "animal": data.get("animal", "unknown"),
        "category": data.get("category", "animal"),
        "timestamp": datetime.now().isoformat(),
        "ts_unix": time.time(),
    }

    _alert_history.append(alert)
    await _broadcast(alert)

    log.info(f"Alert broadcast → {len(_connected_clients)} client(s) | "
             f"{alert['risk_level']} — {alert['title']}")

    return JSONResponse({"ok": True, "clients_notified": len(_connected_clients)})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _connected_clients.add(ws)
    client_addr = ws.client.host if ws.client else "unknown"
    log.info(f"WS client connected: {client_addr}  "
             f"(total: {len(_connected_clients)})")

    # Send welcome + history immediately on connect
    await ws.send_text(json.dumps({
        "type": "connected",
        "message": "Hazard Alert Server ready",
        "history": list(_alert_history),
        "timestamp": datetime.now().isoformat(),
    }))

    try:
        while True:
            # Keep alive — wait for any message (ping) from client
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connected_clients.discard(ws)
        log.info(f"WS client disconnected: {client_addr}  "
                 f"(total: {len(_connected_clients)})")


@app.get("/app", response_class=HTMLResponse)
@app.get("/", response_class=HTMLResponse)
async def serve_app(request: Request):
    """Serve the PWA web app."""
    app_file = Path(__file__).parent / "notification_app" / "index.html"
    if app_file.exists():
        return HTMLResponse(app_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>App not found — make sure notification_app/index.html exists.</h2>",
                        status_code=404)


# ── Entry point ───────────────────────────────────────────────────────────────

def get_local_ips():
    """Return all non-loopback IPv4 addresses."""
    import socket
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ":" not in ip and not ip.startswith("127."):
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    return ips or ["<your-PC-IP>"]


if __name__ == "__main__":
    PORT = int(os.environ.get("NOTIFY_PORT", 8765))
    HOST = "0.0.0.0"

    ips = get_local_ips()
    print()
    print("═" * 60)
    print("    Hazard Alert Notification Server")
    print("═" * 60)
    print(f"  Server      : http://{HOST}:{PORT}")
    print(f"  Status      : http://localhost:{PORT}/status")
    print()
    print("   Open on your phone (same Wi-Fi):")
    for ip in ips:
        print(f"      http://{ip}:{PORT}/app")
    print()
    print("    Open on this PC:")
    print(f"      http://localhost:{PORT}/app")
    print()
    print("    Start the detector (separate terminal):")
    print("      python main.py")
    print("═" * 60)
    print()

    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
