from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from models import (
    Camera,
    CameraGroup,
    User,
    ensure_default_admin,
    ensure_default_camera_group,
    initialize_database,
    verify_password,
)
from scanner import CameraMonitor, NetworkScanner

# ── Scan state ────────────────────────────────────────────────────────────────
_scan_events: list[dict] = []
_scan_stop = threading.Event()
_scan_lock = threading.Lock()
_scan_running = False

# ── Monitor ───────────────────────────────────────────────────────────────────
_monitor: Optional[CameraMonitor] = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _camera_provider() -> list[tuple[str, tuple[int, ...]]]:
    result = []
    for cam in Camera.select():
        ports_str = cam.open_ports_csv or ""
        ports = tuple(int(p) for p in ports_str.split(",") if p.strip().isdigit())
        if not ports:
            ports = (554, 80)
        result.append((cam.ip_address, ports))
    return result


def _status_callback(ip_addr: str, online: bool, latency_ms: Optional[float]) -> None:
    cam = Camera.get_or_none(Camera.ip_address == ip_addr)
    if cam:
        cam.is_online = online
        cam.latency_ms = latency_ms
        if online:
            cam.last_seen_at = utcnow()
        cam.save()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _monitor
    initialize_database()
    ensure_default_admin()
    ensure_default_camera_group()
    _monitor = CameraMonitor(
        camera_provider=_camera_provider,
        status_callback=_status_callback,
        interval_seconds=30,
    )
    _monitor.start()
    yield
    if _monitor:
        _monitor.stop()


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="ip-cam-scanner-secret-2024")
templates = Jinja2Templates(directory="templates")


# ── Auth helpers ──────────────────────────────────────────────────────────────
def get_user(request: Request) -> Optional[User]:
    username = request.session.get("username")
    if not username:
        return None
    return User.get_or_none(User.username == username, User.is_active == True)


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/cameras" if get_user(request) else "/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_user(request):
        return RedirectResponse("/cameras")
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = User.get_or_none(User.username == username, User.is_active == True)
    if user and verify_password(password, bytes(user.password_hash)):
        request.session["username"] = username
        return RedirectResponse("/cameras", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Usuário ou senha inválidos",
    })


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")


# ── Cameras ───────────────────────────────────────────────────────────────────
@app.get("/cameras", response_class=HTMLResponse)
async def cameras_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    groups = list(CameraGroup.select())
    return templates.TemplateResponse("cameras.html", {
        "request": request,
        "user": user,
        "groups": groups,
        "is_admin": user.role == "ADMIN",
    })


@app.get("/partials/cameras", response_class=HTMLResponse)
async def cameras_partial(request: Request, filter: str = "all", search: str = ""):
    user = get_user(request)
    if not user:
        return HTMLResponse("", status_code=401)
    query = Camera.select().order_by(Camera.score.desc())
    if filter == "online":
        query = query.where(Camera.is_online == True)
    elif filter == "offline":
        query = query.where(Camera.is_online == False)
    cameras = list(query)
    if search:
        s = search.lower()
        cameras = [
            c for c in cameras
            if s in (c.ip_address or "").lower()
            or s in (c.brand or "").lower()
            or s in (c.name or "").lower()
        ]
    groups = list(CameraGroup.select())
    return templates.TemplateResponse("partials/camera_table.html", {
        "request": request,
        "cameras": cameras,
        "groups": groups,
        "is_admin": user.role == "ADMIN",
    })


@app.post("/api/cameras", response_class=HTMLResponse)
async def create_camera(
    request: Request,
    name: str = Form(""),
    ip_address: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    brand: str = Form("Desconhecida"),
    location: str = Form(""),
    group_id: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    try:
        group = CameraGroup.get_by_id(int(group_id)) if group_id else None
        Camera.create(
            name=name.strip(),
            ip_address=ip_address.strip(),
            username=username.strip() or None,
            password=password or None,
            brand=brand.strip() or "Desconhecida",
            location=location.strip() or None,
            group=group,
        )
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Erro: {e}</div>")
    return await cameras_partial(request)


@app.post("/api/cameras/{camera_id}/edit", response_class=HTMLResponse)
async def update_camera(
    request: Request,
    camera_id: int,
    name: str = Form(""),
    ip_address: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    brand: str = Form(""),
    location: str = Form(""),
    group_id: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    cam = Camera.get_or_none(Camera.id == camera_id)
    if not cam:
        return HTMLResponse("<div class='alert alert-danger'>Não encontrada</div>", status_code=404)
    try:
        group = CameraGroup.get_by_id(int(group_id)) if group_id else None
        cam.name = name.strip()
        cam.ip_address = ip_address.strip()
        cam.username = username.strip() or None
        cam.password = password or None
        cam.brand = brand.strip() or "Desconhecida"
        cam.location = location.strip() or None
        cam.group = group
        cam.updated_at = utcnow()
        cam.save()
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Erro: {e}</div>")
    return await cameras_partial(request)


@app.post("/api/cameras/{camera_id}/delete", response_class=HTMLResponse)
async def delete_camera(request: Request, camera_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    cam = Camera.get_or_none(Camera.id == camera_id)
    if cam:
        cam.delete_instance()
    return await cameras_partial(request)


# ── Scanner ───────────────────────────────────────────────────────────────────
@app.get("/scanner", response_class=HTMLResponse)
async def scanner_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("scanner.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
        "default_network": NetworkScanner.get_local_network(),
        "scan_running": _scan_running,
    })


@app.post("/api/scan/start")
async def start_scan(request: Request, network: str = Form(...)):
    global _scan_events, _scan_running
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401)

    with _scan_lock:
        if _scan_running:
            return {"status": "already_running"}
        _scan_events = []
        _scan_stop.clear()
        _scan_running = True

    def run():
        global _scan_running
        try:
            ns = NetworkScanner(
                on_progress=lambda done, total: _scan_events.append({
                    "type": "progress",
                    "done": done,
                    "total": total,
                }),
                on_result=lambda r: _scan_events.append({
                    "type": "found",
                    "ip": r.ip,
                    "mac": r.mac or "",
                    "brand": r.brand,
                    "ports": r.open_ports,
                    "score": r.score,
                }),
            )
            ns.scan_network(network.strip(), stop_event=_scan_stop)
        except Exception as e:
            _scan_events.append({"type": "error", "message": str(e)})
        finally:
            _scan_events.append({"type": "done"})
            _scan_running = False

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.post("/api/scan/stop")
async def stop_scan(request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401)
    _scan_stop.set()
    return {"status": "stopped"}


@app.get("/api/scan/events")
async def scan_events(request: Request):
    async def generate() -> AsyncGenerator[str, None]:
        position = 0
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            if position < len(_scan_events):
                event = _scan_events[position]
                yield f"data: {json.dumps(event)}\n\n"
                position += 1
                idle = 0
                if event.get("type") == "done":
                    break
            else:
                await asyncio.sleep(0.15)
                idle += 1
                if idle % 20 == 0:
                    yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/cameras/save-from-scan", response_class=HTMLResponse)
async def save_from_scan(
    request: Request,
    ip_address: str = Form(...),
    brand: str = Form(""),
    open_ports_csv: str = Form(""),
    score: int = Form(0),
    mac_address: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<span class='badge bg-danger'>Sem permissão</span>")
    if Camera.get_or_none(Camera.ip_address == ip_address):
        return HTMLResponse("<span class='badge bg-secondary'>Já salva</span>")
    default_group = CameraGroup.get_or_none(CameraGroup.name == "Minhas Câmeras")
    Camera.create(
        ip_address=ip_address,
        brand=brand or "Desconhecida",
        open_ports_csv=open_ports_csv,
        score=score,
        mac_address=mac_address or None,
        is_online=True,
        last_seen_at=utcnow(),
        group=default_group,
    )
    return HTMLResponse("<span class='badge bg-success'>✓ Salva</span>")


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
