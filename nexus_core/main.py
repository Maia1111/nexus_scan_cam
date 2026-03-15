from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
import subprocess
import time
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import base64
import sqlite3
import httpx
import uvicorn
import io
import os
from xhtml2pdf import pisa
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from models import (
    AppConfig,
    Camera,
    CameraGroup,
    DB_PATH,
    ENC_PREFIX,
    User,
    _VAULT_CHECK_KEY,
    _VAULT_SALT_KEY,
    _derive_fernet_key,
    create_user,
    decrypt_password,
    encrypt_password,
    ensure_default_camera_group,
    has_any_user,
    hash_password,
    initialize_database,
    migrate_existing_passwords,
    restore_database,
    vault_is_configured,
    vault_setup,
    vault_unlock,
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
    # ensure_default_admin()  <-- Removido para forçar o setup manual
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
app.add_middleware(SessionMiddleware, secret_key="nexus-scan-ip-cam-secret-2024")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
templates.env.filters["tojson"] = json.dumps


# ── Auth helpers ──────────────────────────────────────────────────────────────
def get_user(request: Request) -> Optional[User]:
    username = request.session.get("username")
    if not username:
        return None
    return User.get_or_none(User.username == username, User.is_active == True)


# ── Vault helpers ─────────────────────────────────────────────────────────────
_SESSION_VAULT_KEY = "vault_fernet_key"


def get_vault_key(request: Request) -> Optional[bytes]:
    raw = request.session.get(_SESSION_VAULT_KEY)
    return base64.b64decode(raw) if raw else None


def vault_status(request: Request) -> str:
    if not vault_is_configured():
        return "not_configured"
    return "unlocked" if get_vault_key(request) else "locked"


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not has_any_user():
        return RedirectResponse("/setup")
    return RedirectResponse("/cameras" if get_user(request) else "/login")


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if has_any_user():
        return RedirectResponse("/login")
    return templates.TemplateResponse("setup.html", {"request": request})


@app.post("/api/setup", response_class=HTMLResponse)
async def setup_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if has_any_user():
        return HTMLResponse("Ação bloqueada: sistema já configurado.", status_code=403)
    
    if password != confirm_password:
        return HTMLResponse("<div class='alert alert-danger px-2 py-1 small mb-2'>Senhas não conferem</div>")
    
    try:
        user = create_user(username=username, plain_password=password, role="ADMIN")
        request.session["username"] = user.username
        # Redirecionamento via cabeçalho HX-Redirect (para o HTMX entender)
        return Response(headers={"HX-Redirect": "/cameras"})
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger px-2 py-1 small mb-2'>Erro: {e}</div>")


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


@app.get("/cameras/report", response_class=HTMLResponse)
async def cameras_report(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    cameras = list(Camera.select().order_by(Camera.score.desc()))
    online_count = sum(1 for c in cameras if c.is_online)
    return templates.TemplateResponse("report.html", {
        "request": request,
        "title": "Inventário de Câmeras Cadastradas",
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": False,
        "cameras": cameras,
        "cameras_total": len(cameras),
        "online_count": online_count,
        "offline_count": len(cameras) - online_count,
        "issues": [],
        "network_stats": [],
    })


@app.get("/cameras/report/pdf")
async def cameras_report_pdf(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    cameras = list(Camera.select().order_by(Camera.score.desc()))
    online_count = sum(1 for c in cameras if c.is_online)
    html_content = templates.get_template("report.html").render({
        "request": request,
        "title": "Inventário de Câmeras Cadastradas",
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": True,
        "cameras": cameras,
        "cameras_total": len(cameras),
        "online_count": online_count,
        "offline_count": len(cameras) - online_count,
        "issues": [],
        "network_stats": [],
    })
    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        lambda: pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=io.BytesIO()).dest.getvalue()
    )
    filename = f"inventario_cameras_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    is_nvr: bool = Form(False),
    parent_id: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    try:
        group = CameraGroup.get_by_id(int(group_id)) if group_id else None
        fernet_key = get_vault_key(request)
        final_password = encrypt_password(password, fernet_key) if (password and fernet_key) else password or None
        Camera.create(
            name=name.strip(),
            ip_address=ip_address.strip(),
            username=username.strip() or None,
            password=final_password,
            brand=brand.strip() or "Desconhecida",
            location=location.strip() or None,
            group=group,
            is_nvr=is_nvr,
            parent=Camera.get_by_id(int(parent_id)) if parent_id else None,
        )
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Erro: {e}</div>")
    return await cameras_partial(request)


@app.post("/api/cameras/{camera_id}/credentials", response_class=HTMLResponse)
async def update_camera_credentials(
    request: Request,
    camera_id: int,
    username: str = Form(""),
    password: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    cam = Camera.get_or_none(Camera.id == camera_id)
    if not cam:
        return HTMLResponse("<div class='alert alert-danger'>Câmera não encontrada</div>", status_code=404)
    cam.username = username.strip() or None
    if password.strip():
        fernet_key = get_vault_key(request)
        cam.password = encrypt_password(password, fernet_key) if fernet_key else password
    cam.updated_at = utcnow()
    cam.save()
    return HTMLResponse("<div class='alert alert-success py-2'><i class='bi bi-check-circle me-1'></i>Credenciais salvas!</div>")


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
    is_nvr: bool = Form(False),
    parent_id: str = Form(""),
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
        if password.strip():
            fernet_key = get_vault_key(request)
            cam.password = encrypt_password(password, fernet_key) if fernet_key else password
        # se senha em branco, mantém a senha atual
        cam.brand = brand.strip() or "Desconhecida"
        cam.location = location.strip() or None
        cam.group = group
        cam.is_nvr = is_nvr
        cam.parent = Camera.get_by_id(int(parent_id)) if parent_id else None
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
    try:
        cam = Camera.get_or_none(Camera.id == camera_id)
        if cam:
            # Primeiro remove vínculos de filhos para evitar erro de FK
            Camera.update(parent=None).where(Camera.parent == cam).execute()
            cam.delete_instance()
        return await cameras_partial(request)
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger font-monospace small'>Erro ao excluir: {str(e)}</div>")


@app.post("/api/cameras/bulk-delete", response_class=HTMLResponse)
async def bulk_delete_cameras(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    body = await request.json()
    ids = body.get("ids", [])
    for cid in ids:
        cam = Camera.get_or_none(Camera.id == cid)
        if cam:
            Camera.update(parent=None).where(Camera.parent == cam).execute()
            cam.delete_instance()
    return await cameras_partial(request)


# ── Scanner ───────────────────────────────────────────────────────────────────
@app.get("/scanner", response_class=HTMLResponse)
async def page_scanner(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    
    networks = NetworkScanner.get_all_networks()
    default_net = networks[0] if networks else "192.168.1.0/24"
    
    saved_ips = [row[0] for row in Camera.select(Camera.ip_address).tuples()]
    return templates.TemplateResponse("scanner.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
        "default_network": default_net,
        "detected_networks": networks,
        "scan_running": _scan_running,
        "saved_ips": list(saved_ips),
    })


@app.get("/api/scan/networks")
async def api_get_networks():
    return {"networks": NetworkScanner.get_all_networks()}


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
                    "mac": r.mac,
                    "brand": r.brand,
                    "ports": r.open_ports,
                    "score": r.score,
                    "is_nvr": r.is_nvr,
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
    name: str = Form(""),
    is_nvr: bool = Form(False),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<span class='badge bg-danger'>Sem permissão</span>")
    if Camera.get_or_none(Camera.ip_address == ip_address):
        return HTMLResponse("<span class='badge bg-secondary'>Já salva</span>")
    default_group = CameraGroup.get_or_none(CameraGroup.name == "Minhas Câmeras")
    Camera.create(
        name=name.strip(),
        ip_address=ip_address,
        brand=brand or "Desconhecida",
        open_ports_csv=open_ports_csv,
        score=score,
        mac_address=mac_address or None,
        is_online=True,
        last_seen_at=utcnow(),
        group=default_group,
        is_nvr=is_nvr,
    )
    label = name.strip() or ip_address
    return HTMLResponse(f"<span class='badge bg-success'>✓ {label}</span>")


# ── Traceroute ───────────────────────────────────────────────────────────────
@app.get("/api/cameras/traceroute")
async def camera_traceroute(ip: str, request: Request):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401)

    # Tabela ARP para resolução de MAC
    arp_map: dict[str, str] = {}
    try:
        arp_out = subprocess.run(
            ["arp", "-a"], capture_output=True, timeout=5,
        ).stdout.decode(errors="replace")
        for line in arp_out.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\w-]{11,17})", line)
            if m:
                arp_map[m.group(1)] = m.group(2).upper()
    except Exception:
        pass

    # Identificar o IP local do servidor para marcar no traceroute
    server_ip = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            server_ip = s.getsockname()[0]
    except Exception:
        pass

    # Traceroute
    hops = []
    try:
        result = subprocess.run(
            ["tracert", "-d", "-w", "2000", "-h", "20", ip],
            capture_output=True, timeout=90,
        ).stdout.decode(errors="replace")

        for line in result.splitlines():
            m = re.match(r"\s*(\d+)\s+.*?(\d+\.\d+\.\d+\.\d+)\s*$", line)
            if m:
                hop_ip = m.group(2)
                hops.append({
                    "hop": int(m.group(1)),
                    "ip": hop_ip,
                    "mac": arp_map.get(hop_ip, ""),
                    "timeout": False,
                    "is_server": (hop_ip == server_ip),
                })
            elif re.match(r"\s*(\d+)\s+\*", line):
                n = int(re.match(r"\s*(\d+)", line).group(1))
                hops.append({"hop": n, "ip": "*", "mac": "", "timeout": True, "is_server": False})
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Adicionar lógica de NVR ao rastro
    nvr_info = None
    cam = Camera.get_or_none(Camera.ip_address == ip)
    if cam and cam.parent:
        nvr_info = {
            "name": cam.parent.name or cam.parent.ip_address,
            "ip": cam.parent.ip_address,
            "is_online": cam.parent.is_online
        }

    return {
        "target": ip, 
        "hops": hops, 
        "server_ip": server_ip,
        "nvr_info": nvr_info
    }


# ── Groups ───────────────────────────────────────────────────────────────────
@app.get("/groups", response_class=HTMLResponse)
async def groups_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
    })


@app.get("/partials/groups", response_class=HTMLResponse)
async def groups_partial(request: Request):
    user = get_user(request)
    if not user:
        return HTMLResponse("", status_code=401)
    groups = list(CameraGroup.select())
    groups_data = []
    for g in groups:
        cam_count = Camera.select().where(Camera.group == g).count()
        groups_data.append({"group": g, "cam_count": cam_count})
    all_cameras = list(Camera.select().order_by(Camera.name, Camera.ip_address))
    return templates.TemplateResponse("partials/groups_list.html", {
        "request": request,
        "groups_data": groups_data,
        "all_cameras": all_cameras,
        "is_admin": user.role == "ADMIN",
    })


@app.post("/api/groups", response_class=HTMLResponse)
async def create_group(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    try:
        CameraGroup.create(
            name=name.strip(),
            description=description.strip(),
            latitude=float(latitude) if latitude.strip() else None,
            longitude=float(longitude) if longitude.strip() else None,
        )
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Erro: {e}</div>")
    return await groups_partial(request)


@app.post("/api/groups/{group_id}/edit", response_class=HTMLResponse)
async def update_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    description: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    grp = CameraGroup.get_or_none(CameraGroup.id == group_id)
    if not grp:
        return HTMLResponse("<div class='alert alert-danger'>Grupo não encontrado</div>", status_code=404)
    try:
        grp.name = name.strip()
        grp.description = description.strip()
        grp.latitude = float(latitude) if latitude.strip() else None
        grp.longitude = float(longitude) if longitude.strip() else None
        grp.save()
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Erro: {e}</div>")
    return await groups_partial(request)


@app.post("/api/groups/{group_id}/delete", response_class=HTMLResponse)
async def delete_group(request: Request, group_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    grp = CameraGroup.get_or_none(CameraGroup.id == group_id)
    if grp:
        grp.delete_instance()
    return await groups_partial(request)


@app.post("/api/groups/{group_id}/add-camera", response_class=HTMLResponse)
async def add_camera_to_group(
    request: Request,
    group_id: int,
    camera_id: str = Form(...),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    grp = CameraGroup.get_or_none(CameraGroup.id == group_id)
    cam = Camera.get_or_none(Camera.id == int(camera_id))
    if grp and cam:
        cam.group = grp
        cam.save()
    return await groups_partial(request)


@app.post("/api/groups/{group_id}/remove-camera/{camera_id}", response_class=HTMLResponse)
async def remove_camera_from_group(request: Request, group_id: int, camera_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    cam = Camera.get_or_none(Camera.id == camera_id)
    if cam:
        cam.group = None
        cam.save()
    return await groups_partial(request)


# ── Diagnostics helpers ───────────────────────────────────────────────────────
def _get_local_ips() -> list[str]:
    """Retorna todos os IPs IPv4 da máquina, excluindo loopback."""
    try:
        hostname = socket.gethostname()
        return list({
            info[4][0]
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET)
            if not info[4][0].startswith("127.")
        })
    except Exception:
        return []


async def _tcp_ping_once(ip: str, port: int, timeout: float) -> float | None:
    """Tenta uma conexão TCP assíncrona e retorna a latência em ms, ou None se falhar."""
    try:
        t0 = time.perf_counter()
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        ms = (time.perf_counter() - t0) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return ms
    except Exception:
        return None


async def _tcp_ping_multi(ip: str, port: int, count: int = 3, timeout: float = 1.0) -> dict:
    """Pinga via TCP `count` vezes em paralelo e retorna métricas de latência/perda."""
    samples: list[float | None] = await asyncio.gather(
        *[_tcp_ping_once(ip, port, timeout) for _ in range(count)]
    )
    ok = [s for s in samples if s is not None]
    fail = len(samples) - len(ok)
    avg = sum(ok) / len(ok) if ok else None
    jitter = (max(ok) - min(ok)) if len(ok) > 1 else 0.0
    return {
        "reachable": len(ok) > 0,
        "avg_ms": avg,
        "max_ms": max(ok) if ok else None,
        "min_ms": min(ok) if ok else None,
        "jitter_ms": jitter,
        "loss_pct": (fail / count) * 100,
    }


async def _collect_diagnostics(group_id: Optional[int] = None) -> dict:
    """Executa todas as verificações e retorna issues + network_stats."""
    issues: list[dict] = []
    
    if group_id:
        cameras = list(Camera.select().where(Camera.group_id == group_id))
    else:
        cameras = list(Camera.select())

    # Verifica cobertura de interface de rede local
    local_ips = _get_local_ips()
    if local_ips and cameras:
        local_subnets = set()
        for ip in local_ips:
            try:
                local_subnets.add(ipaddress.ip_network(ip + "/24", strict=False))
            except Exception:
                pass

        cam_subnets: dict[str, list] = {}
        for cam in cameras:
            try:
                net = ipaddress.ip_network(cam.ip_address + "/24", strict=False)
                cam_subnets.setdefault(str(net), []).append(cam)
            except Exception:
                pass

        for subnet_str, cams in cam_subnets.items():
            subnet = ipaddress.ip_network(subnet_str)
            if not any(subnet.overlaps(local) for local in local_subnets):
                issues.append({
                    "severity": "warning",
                    "icon": "ethernet",
                    "type": "no_local_interface",
                    "title": f"Interface não configurada para a faixa {subnet_str}",
                    "detail": (
                        f"{len(cams)} câmera(s) cadastrada(s) em {subnet_str}, mas este computador "
                        f"não possui nenhum endereço IP nessa faixa. "
                        f"IPs locais detectados: {', '.join(local_ips)}."
                    ),
                    "suggestion": f"Acesse Painel de Controle → Conexões de Rede → Propriedades da placa → TCP/IPv4 e adicione um IP secundário na faixa {subnet_str} (ex: primeiro endereço disponível da faixa).",
                })

    # Verificações estáticas
    for cam in cameras:
        if not cam.is_online and cam.last_seen_at:
            issues.append({
                "severity": "warning", "icon": "wifi-off",
                "type": "offline", "title": "Câmera offline",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — última resposta em {cam.last_seen_at.strftime('%d/%m/%Y %H:%M')}",
                "suggestion": "Verifique: 1) alimentação da câmera; 2) cabo de rede e conector; 3) porta do switch (troque de porta para testar); 4) tente pingar manualmente pelo CMD: ping " + cam.ip_address,
                "camera": cam,
            })
    for cam in cameras:
        if cam.last_seen_at is None:
            issues.append({
                "severity": "info", "icon": "question-circle",
                "type": "never_seen", "title": "Nunca respondeu",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — cadastrada mas nunca foi vista online",
                "suggestion": f"Confirme se o IP está correto tentando abrir http://{cam.ip_address} no navegador. Se necessário, refaça o scanner ou edite o cadastro com o IP correto.",
                "camera": cam,
            })
    arp_map = NetworkScanner.parse_arp_table()
    for cam in cameras:
        if cam.mac_address and cam.ip_address in arp_map:
            current = arp_map[cam.ip_address].upper()
            saved = cam.mac_address.upper()
            if current != saved:
                issues.append({
                    "severity": "danger", "icon": "shield-exclamation",
                    "type": "ip_conflict", "title": "Conflito IP/MAC",
                    "detail": f"IP {cam.ip_address} agora responde com MAC {current} (salvo: {saved}). Possível substituição ou invasão.",
                    "suggestion": f"Outro dispositivo pode estar usando o IP {cam.ip_address}. Acesse o switch e identifique qual porta tem o MAC {current}. Se for substituição de câmera, atualize o cadastro com o novo MAC.",
                    "camera": cam,
                })
    mac_map: dict[str, list] = {}
    for cam in cameras:
        if cam.mac_address:
            mac_map.setdefault(cam.mac_address.upper(), []).append(cam)
    for mac, cams in mac_map.items():
        if len(cams) > 1:
            issues.append({
                "severity": "warning", "icon": "diagram-2",
                "type": "duplicate_mac", "title": "MAC duplicado",
                "detail": f"MAC {mac} em {len(cams)} IPs: {', '.join(c.ip_address for c in cams)}.",
                "suggestion": "MACs duplicados geralmente indicam cadastro incorreto. Verifique se os IPs pertencem ao mesmo equipamento físico. Se for câmera diferente, corrija o MAC no cadastro.",
                "camera": cams[0],
            })
    for cam in cameras:
        if not cam.username:
            issues.append({
                "severity": "info", "icon": "key",
                "type": "no_credentials", "title": "Sem credenciais",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — sem usuário/senha cadastrado",
                "suggestion": "Cadastre as credenciais em Administração → Cofre de Senhas para mantê-las criptografadas. Ou use o botão de chave no diagnóstico para cadastro rápido.",
                "camera": cam,
            })

    # 6. Câmeras com IP dinâmico (DHCP) — MAC encontrado em IP diferente do salvo
    mac_to_current_ip: dict[str, str] = {}
    for arp_ip, arp_mac in arp_map.items():
        mac_to_current_ip[arp_mac.upper()] = arp_ip

    for cam in cameras:
        if cam.mac_address:
            mac = cam.mac_address.upper()
            current_ip = mac_to_current_ip.get(mac)
            if current_ip and current_ip != cam.ip_address:
                issues.append({
                    "severity": "warning", "icon": "arrow-repeat",
                    "type": "dhcp", "title": "IP dinâmico detectado (DHCP)",
                    "detail": (
                        f"{cam.name or cam.ip_address}: MAC {cam.mac_address} agora está no IP {current_ip} "
                        f"(cadastrado como {cam.ip_address}). A câmera provavelmente usa DHCP."
                    ),
                    "suggestion": f"Opção 1: Acesse a câmera e configure IP estático ({cam.ip_address} ou outro fixo). Opção 2: No roteador, crie uma reserva DHCP para o MAC {cam.mac_address} sempre receber o mesmo IP. Depois atualize o cadastro aqui se o IP mudar.",
                    "camera": cam,
                })

    # 7. NVR/DVR detectado — múltiplas portas de gestão abertas simultaneamente
    NVR_PORTS = {80, 443, 554, 8000, 37777, 34567, 8554}
    NVR_THRESHOLD = 3
    for cam in cameras:
        ports = {int(p) for p in (cam.open_ports_csv or "").split(",") if p.strip().isdigit()}
        nvr_ports_open = ports & NVR_PORTS
        if len(nvr_ports_open) >= NVR_THRESHOLD and cam.score >= 70:
            issues.append({
                "severity": "info", "icon": "hdd-network",
                "type": "nvr", "title": "Possível NVR/DVR detectado",
                "detail": (
                    f"{cam.name or cam.ip_address} ({cam.ip_address}) — {len(nvr_ports_open)} portas de gerenciamento abertas: "
                    f"{', '.join(str(p) for p in sorted(nvr_ports_open))}. "
                    f"Dispositivo provavelmente é um gravador (NVR/DVR). "
                    f"Cadastre as câmeras individuais conectadas a ele separadamente."
                ),
                "camera": cam,
            })

    # Verificações ativas (TCP ping)
    network_stats: list[dict] = []
    if cameras:
        def _get_port(cam: Camera) -> int:
            ports = [int(p) for p in (cam.open_ports_csv or "").split(",") if p.strip().isdigit()]
            return ports[0] if ports else 554

        sem = asyncio.Semaphore(80)

        async def _ping_with_sem(cam):
            async with sem:
                return await _tcp_ping_multi(cam.ip_address, _get_port(cam))

        ping_results = await asyncio.gather(*[_ping_with_sem(cam) for cam in cameras])
        for cam, p in zip(cameras, ping_results):
            label = cam.name or cam.ip_address
            if cam.is_online and not p["reachable"]:
                issues.append({
                    "severity": "danger", "icon": "slash-circle",
                    "type": "frozen", "title": "Câmera não responde (possível travamento)",
                    "detail": f"{label} ({cam.ip_address}) marcada como online mas não respondeu a nenhum dos 3 pings TCP.",
                    "suggestion": "Reinicie a câmera (desconecte e reconecte a alimentação). Se o problema persistir, acesse a interface web e verifique os logs. Câmeras que travam periodicamente geralmente precisam de atualização de firmware.",
                    "camera": cam,
                })
            elif p["reachable"]:
                avg, jitter, loss = p["avg_ms"], p["jitter_ms"], p["loss_pct"]
                if avg > 300:
                    issues.append({"severity": "danger", "icon": "speedometer", "type": "high_latency",
                        "title": "Latência crítica — possível loop de rede",
                        "detail": f"{label}: latência média {avg:.0f}ms. Referência: <20ms normal · 20–80ms aceitável · >80ms atenção · >300ms crítico.",
                        "suggestion": "Latência >300ms em LAN quase sempre indica loop de switch ou broadcast storm. Verifique a topologia de rede, desative portas suspeitas e confirme que o STP (Spanning Tree) está ativo nos switches.",
                        "camera": cam})
                elif avg > 80:
                    issues.append({"severity": "warning", "icon": "speedometer2", "type": "high_latency",
                        "title": "Latência alta",
                        "detail": f"{label}: latência {avg:.0f}ms. Referência: <20ms normal · 20–80ms aceitável · >80ms atenção.",
                        "suggestion": "Verifique: 1) qualidade do cabo (troque por um novo para testar); 2) troque a porta no switch; 3) verifique se o switch está sobrecarregado ou com firmware desatualizado.",
                        "camera": cam})
                if jitter > 100:
                    issues.append({"severity": "danger", "icon": "graph-up-arrow", "type": "jitter",
                        "title": "Instabilidade grave (jitter alto)",
                        "detail": f"{label}: jitter {jitter:.0f}ms. Referência: <10ms normal · 10–40ms aceitável · >40ms atenção · >100ms crítico.",
                        "suggestion": "Jitter >100ms indica loop de rede ou broadcast storm. Verifique topologia de switch, cabos e configuração de STP. Pode também ser causado por saturação de banda.",
                        "camera": cam})
                elif jitter > 40:
                    issues.append({"severity": "warning", "icon": "graph-up", "type": "jitter",
                        "title": "Conexão instável",
                        "detail": f"{label}: jitter {jitter:.0f}ms. Referência: <10ms normal · 10–40ms aceitável · >40ms problema.",
                        "suggestion": "Jitter elevado geralmente indica cabo com problema intermitente ou conector oxidado. Troque o cabo ou a porta do switch. Evite Wi-Fi para câmeras de segurança.",
                        "camera": cam})
                if loss >= 50:
                    issues.append({"severity": "danger", "icon": "reception-0", "type": "packet_loss",
                        "title": f"Perda de pacotes grave: {loss:.0f}%",
                        "detail": f"{label}: {loss:.0f}% dos pacotes TCP perdidos. Qualquer perda em LAN cabeada é anormal.",
                        "suggestion": "Perda ≥50% indica falha grave no meio físico. Substitua o cabo imediatamente. Se persistir após trocar o cabo, a porta do switch ou a própria câmera pode estar com defeito.",
                        "camera": cam})
                elif loss > 0:
                    issues.append({"severity": "warning", "icon": "reception-2", "type": "packet_loss",
                        "title": f"Perda de pacotes: {loss:.0f}%",
                        "detail": f"{label}: {loss:.0f}% dos pacotes perdidos. Em rede cabeada LAN o esperado é 0%.",
                        "suggestion": "Qualquer perda de pacotes em LAN cabeada indica problema físico. Troque o cabo ou a porta do switch. Verifique conectores RJ45 (crimpagem solta ou oxidada).",
                        "camera": cam})

            network_stats.append({
                "cam": cam, "reachable": p["reachable"],
                "avg_ms": p["avg_ms"], "jitter_ms": p["jitter_ms"], "loss_pct": p["loss_pct"],
            })

    def _classify(s: dict) -> str:
        if not s["reachable"]:
            return "offline"
        avg = s["avg_ms"] or 0
        jitter = s["jitter_ms"] or 0
        loss = s["loss_pct"] or 0
        if avg > 300 or jitter > 100 or loss >= 50:
            return "critico"
        if avg > 80 or jitter > 40 or loss > 0:
            return "atencao"
        return "normal"

    stats_offline  = [s for s in network_stats if _classify(s) == "offline"]
    stats_critico  = [s for s in network_stats if _classify(s) == "critico"]
    stats_atencao  = [s for s in network_stats if _classify(s) == "atencao"]
    stats_normal   = [s for s in network_stats if _classify(s) == "normal"]

    # Attach per-camera warning/danger labels+suggestions to atencao and critico rows
    _warn_map: dict[int, list[dict]] = {}
    for iss in issues:
        if iss.get("severity") in ("warning", "danger") and iss.get("camera"):
            cid = iss["camera"].id
            _warn_map.setdefault(cid, []).append({
                "title": iss["title"],
                "suggestion": iss.get("suggestion", ""),
            })
    for s in stats_atencao + stats_critico:
        s["cam_warnings"] = _warn_map.get(s["cam"].id, [])

    # Structural warnings (no specific camera, e.g. duplicate MAC)
    warnings_structural = [i for i in issues if i.get("severity") == "warning" and not i.get("camera")]

    return {
        "issues": issues,
        "network_stats": network_stats,
        "stats_offline": stats_offline,
        "stats_critico": stats_critico,
        "stats_atencao": stats_atencao,
        "stats_normal":  stats_normal,
        "warnings_structural": warnings_structural,
        "cameras": cameras,
        "cameras_total": len(cameras),
        "online_count": sum(1 for c in cameras if c.is_online),
        "offline_count": sum(1 for c in cameras if not c.is_online),
    }


# ── Diagnostics ───────────────────────────────────────────────────────────────
@app.get("/diagnostics", response_class=HTMLResponse)
async def diagnostics_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("diagnostics.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
    })


@app.get("/api/diagnostics/run", response_class=HTMLResponse)
async def run_diagnostics(request: Request):
    user = get_user(request)
    if not user:
        return HTMLResponse("", status_code=401)
    data = await _collect_diagnostics()
    return templates.TemplateResponse("partials/diagnostics_result.html", {"request": request, **data})


@app.get("/diagnostics/report", response_class=HTMLResponse)
async def diagnostics_report(request: Request, group_id: Optional[int] = None):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    data = await _collect_diagnostics(group_id=group_id)
    
    title = "Relatório de Saúde da Rede"
    if group_id:
        group = CameraGroup.get_or_none(CameraGroup.id == group_id)
        if group:
            title = f"Relatório — Grupo: {group.name}"

    return templates.TemplateResponse("report.html", {
        "request": request,
        "title": title,
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": False,
        **data,
    })


@app.get("/diagnostics/report/pdf")
async def diagnostics_report_pdf(request: Request, group_id: Optional[int] = None):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")

    data = await _collect_diagnostics(group_id=group_id)
    
    title = "Relatório de Saúde da Rede"
    prefix = "relatorio_cameras"
    if group_id:
        group = CameraGroup.get_or_none(CameraGroup.id == group_id)
        if group:
            title = f"Relatório — Grupo: {group.name}"
            prefix = f"relatorio_grupo_{group.name.replace(' ', '_').lower()}"

    html_content = templates.get_template("report.html").render({
        "request": request,
        "title": title,
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": True,
        **data,
    })

    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        lambda: pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=io.BytesIO()).dest.getvalue()
    )

    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _collect_grouped_diagnostics() -> dict:
    """Coleta diagnósticos e agrupa por CameraGroup."""
    data = await _collect_diagnostics()
    
    # Organiza os resultados por grupo
    # Estrutura: { group_id: { group: GroupObj, cameras: [], issues: [], stats: [], total: 0, online: 0, offline: 0 } }
    grouped = {}
    
    # Garante que todos os grupos existentes estejam no dicionário
    for group in CameraGroup.select():
        grouped[group.id] = {
            "group": group,
            "cameras": [],
            "issues": [],
            "stats": [],
            "online": 0,
            "offline": 0
        }
    
    # Caso especial para câmeras sem grupo (None)
    no_group_key = 0
    grouped[no_group_key] = {
        "group": {"id": 0, "name": "Sem Grupo Escalar"},
        "cameras": [],
        "issues": [],
        "stats": [],
        "online": 0,
        "offline": 0
    }

    # Distribui as câmeras
    for cam in data["cameras"]:
        gid = cam.group_id if cam.group_id else no_group_key
        if gid not in grouped: # Caso o grupo tenha sido deletado mas a câmera ainda aponte pra ele
            continue
        grouped[gid]["cameras"].append(cam)
        if cam.is_online:
            grouped[gid]["online"] += 1
        else:
            grouped[gid]["offline"] += 1

    # Distribui os issues
    for issue in data["issues"]:
        cam = issue.get("camera")
        if cam:
            gid = cam.group_id if cam.group_id else no_group_key
            if gid in grouped:
                grouped[gid]["issues"].append(issue)

    # Distribui as métricas de rede (stats)
    for stat in data["network_stats"]:
        cam = stat.get("cam")
        if cam:
            gid = cam.group_id if cam.group_id else no_group_key
            if gid in grouped:
                grouped[gid]["stats"].append(stat)

    # Remove grupos vazios (opcional, mas melhor para o relatório)
    final_groups = []
    for gid in sorted(grouped.keys()):
        g_data = grouped[gid]
        if g_data["cameras"]:
            g_data["total"] = len(g_data["cameras"])
            final_groups.append(g_data)
            
    return {
        "groups": final_groups,
        "total_groups": len(final_groups),
        "total_cameras": data["cameras_total"],
        "total_online": data["online_count"],
        "total_offline": data["offline_count"],
        "total_issues": len(data["issues"])
    }


@app.get("/diagnostics/groups/report", response_class=HTMLResponse)
async def diagnostics_grouped_report(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    data = await _collect_grouped_diagnostics()
    return templates.TemplateResponse("report_grouped.html", {
        "request": request,
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": False,
        **data,
    })


@app.get("/diagnostics/groups/report/pdf")
async def diagnostics_grouped_report_pdf(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")

    data = await _collect_grouped_diagnostics()
    html_content = templates.get_template("report_grouped.html").render({
        "request": request,
        "generated_at": datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "generated_by": user.username,
        "for_print": True,
        **data,
    })

    loop = asyncio.get_running_loop()
    pdf_bytes = await loop.run_in_executor(
        None,
        lambda: pisa.CreatePDF(io.BytesIO(html_content.encode("utf-8")), dest=io.BytesIO()).dest.getvalue()
    )

    filename = f"relatorio_agrupado_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Camera snapshot viewer ─────────────────────────────────────────────────────
_SNAPSHOT_URLS = [
    # Intelbras VIP (baseado em Hikvision)
    "http://{ip}/ISAPI/Streaming/channels/101/picture",
    "http://{ip}/Streaming/channels/1/picture",
    # Intelbras VHD/VM (baseado em Dahua)
    "http://{ip}/cgi-bin/snapshot.cgi",
    "http://{ip}/cgi-bin/snapshot.cgi?channel=1&subtype=0",
    "http://{ip}/cgi-bin/mjpg/video.cgi?channel=0&subtype=1",
    # Genéricas
    "http://{ip}/snapshot.jpg",
    "http://{ip}/snap.jpg",
    "http://{ip}/tmpfs/snap.jpg",
    "http://{ip}/onvif/snapshot",
    "http://{ip}:8080/snapshot.jpg",
    "http://{ip}/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2",
]


async def _dahua_snapshot(ip: str, username: str, password: str) -> bytes | None:
    """Login via RPC2 (Dahua/Intelbras VHD) e captura snapshot."""
    import hashlib

    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        try:
            # Passo 1: pegar challenge
            r1 = await client.post(f"http://{ip}/RPC2_Login", json={
                "method": "global.login",
                "params": {"userName": username, "password": "", "clientType": "Web3.0"},
                "id": 1,
            })
            data1 = r1.json()
            params = data1.get("params") or {}
            realm = params.get("realm", "")
            random_val = params.get("random", "")
            session = data1.get("session", "")
            if not realm:
                return None

            # Passo 2: calcular hash Dahua
            pwd1 = hashlib.md5(password.encode()).hexdigest().upper()
            pwd2 = hashlib.md5(f"{username}:{realm}:{pwd1}".encode()).hexdigest()

            # Passo 3: login com hash
            r2 = await client.post(f"http://{ip}/RPC2_Login", json={
                "method": "global.login",
                "params": {
                    "userName": username,
                    "password": pwd2,
                    "clientType": "Web3.0",
                    "authorityType": "Default",
                },
                "session": session,
                "id": 2,
            })
            data2 = r2.json()
            if not data2.get("result"):
                print(f"[Snapshot Dahua] Login falhou: {data2}")
                return None

            # Passo 4: capturar snapshot com cookie de sessão
            cookies = {"DhWebClientSessionID": session}
            for path in ["/cgi-bin/snapshot.cgi", "/cgi-bin/snapshot.cgi?channel=1"]:
                r3 = await client.get(f"http://{ip}{path}", cookies=cookies)
                ct = r3.headers.get("content-type", "")
                if r3.status_code == 200 and "image" in ct:
                    print(f"[Snapshot Dahua] SUCESSO: {path}")
                    return r3.content

        except Exception as e:
            print(f"[Snapshot Dahua] Erro: {e}")

    return None


@app.get("/api/cameras/{camera_id}/snapshot")
async def camera_snapshot(
    request: Request,
    camera_id: int,
    username: str = "",
    password: str = "",
):
    user = get_user(request)
    if not user:
        raise HTTPException(status_code=401)

    cam = Camera.get_or_none(Camera.id == camera_id)
    if not cam:
        raise HTTPException(status_code=404)

    fernet_key = get_vault_key(request)
    u = username or cam.username or ""
    stored_pass = cam.password or ""
    p = password or (decrypt_password(stored_pass, fernet_key) if fernet_key else stored_pass) or ""
    auth = (u, p) if u else None

    print(f"[Snapshot] Solicitando imagem para {cam.ip_address} (ID: {camera_id})")

    # Tenta login Dahua/Intelbras VHD primeiro (RPC2 challenge-response)
    if u:
        data = await _dahua_snapshot(cam.ip_address, u, p)
        if data:
            return Response(content=data, media_type="image/jpeg")

    # Fallback: URLs genéricas com Basic/Digest Auth
    async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
        for url_tpl in _SNAPSHOT_URLS:
            url = url_tpl.format(ip=cam.ip_address)
            try:
                resp = await client.get(url, auth=auth)
                if resp.status_code == 401 and u:
                    from httpx import DigestAuth
                    resp = await client.get(url, auth=DigestAuth(u, p))
                print(f"[Snapshot] {url} -> {resp.status_code}")
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and "image" in ct:
                    print(f"[Snapshot] SUCESSO: {url}")
                    return Response(content=resp.content, media_type=ct)
            except Exception as e:
                print(f"[Snapshot] Erro em {url}: {e}")
                continue

    raise HTTPException(status_code=404, detail="Snapshot não disponível para esta câmera")


# ── Vault ─────────────────────────────────────────────────────────────────────
@app.get("/admin/vault", response_class=HTMLResponse)
async def vault_page(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin_vault.html", {
        "request": request,
        "user": user,
        "is_admin": True,
        "vault_status": vault_status(request),
    })


@app.post("/api/vault/setup", response_class=HTMLResponse)
async def vault_setup_route(
    request: Request,
    master_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    if vault_is_configured():
        return HTMLResponse("<div class='alert alert-danger'>Cofre já configurado.</div>")
    if master_password != confirm_password:
        return HTMLResponse("<div class='alert alert-danger'>Senhas não conferem.</div>")
    if len(master_password) < 6:
        return HTMLResponse("<div class='alert alert-danger'>Senha mestra deve ter ao menos 6 caracteres.</div>")
    fernet_key = vault_setup(master_password)
    count = migrate_existing_passwords(fernet_key)
    request.session[_SESSION_VAULT_KEY] = base64.b64encode(fernet_key).decode()
    return HTMLResponse(
        f"<div class='alert alert-success'>"
        f"<i class='bi bi-check-circle me-1'></i>Cofre configurado! {count} senha(s) criptografada(s)."
        f"<script>setTimeout(()=>location.reload(),1500)</script></div>"
    )


@app.post("/api/vault/unlock", response_class=HTMLResponse)
async def vault_unlock_route(request: Request, master_password: str = Form(...)):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    fernet_key = vault_unlock(master_password)
    if not fernet_key:
        return HTMLResponse("<div class='alert alert-danger'>Senha mestra incorreta.</div>")
    request.session[_SESSION_VAULT_KEY] = base64.b64encode(fernet_key).decode()
    return HTMLResponse(
        "<div class='alert alert-success'><i class='bi bi-check-circle me-1'></i>Cofre desbloqueado!"
        "<script>setTimeout(()=>location.reload(),800)</script></div>"
    )


@app.post("/api/vault/lock")
async def vault_lock_route(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        raise HTTPException(status_code=403)
    request.session.pop(_SESSION_VAULT_KEY, None)
    return RedirectResponse("/admin/vault", status_code=303)


@app.get("/partials/vault/cameras", response_class=HTMLResponse)
async def vault_cameras_partial(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("", status_code=401)
    fernet_key = get_vault_key(request)
    if not fernet_key:
        return HTMLResponse("<div class='alert alert-warning'>Cofre bloqueado.</div>")
    cameras = list(
        Camera.select()
        .where((Camera.username.is_null(False)) | (Camera.password.is_null(False)))
        .order_by(Camera.ip_address)
    )
    return templates.TemplateResponse("partials/vault_camera_table.html", {
        "request": request,
        "cameras": cameras,
        "ENC_PREFIX": ENC_PREFIX,
    })


@app.post("/api/vault/reveal/{camera_id}")
async def vault_reveal(request: Request, camera_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        raise HTTPException(status_code=403)
    fernet_key = get_vault_key(request)
    if not fernet_key:
        raise HTTPException(status_code=403, detail="Cofre bloqueado.")
    cam = Camera.get_or_none(Camera.id == camera_id)
    if not cam:
        raise HTTPException(status_code=404)
    plain = decrypt_password(cam.password or "", fernet_key)
    return {"password": plain}


# ── Profile ───────────────────────────────────────────────────────────────────
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
        "vault_configured": vault_is_configured(),
        "vault_unlocked": get_vault_key(request) is not None,
    })


@app.post("/api/profile/password", response_class=HTMLResponse)
async def profile_change_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = get_user(request)
    if not user:
        return HTMLResponse('<div class="alert alert-danger">Não autenticado.</div>', status_code=401)
    if len(new_password) < 6:
        return HTMLResponse('<div class="alert alert-danger">A nova senha deve ter pelo menos 6 caracteres.</div>', status_code=400)
    if new_password != confirm_password:
        return HTMLResponse('<div class="alert alert-danger">As senhas não coincidem.</div>', status_code=400)
    User.update(password_hash=hash_password(new_password)).where(User.id == user.id).execute()
    return HTMLResponse('<div class="alert alert-success">Senha alterada com sucesso.</div>')


@app.post("/api/profile/vault/unlock", response_class=HTMLResponse)
async def profile_vault_unlock(request: Request, master_password: str = Form(...)):
    user = get_user(request)
    if not user:
        return HTMLResponse('<div class="alert alert-danger">Não autenticado.</div>', status_code=401)
    if not vault_is_configured():
        return HTMLResponse('<div class="alert alert-danger">Cofre não configurado.</div>', status_code=400)
    fernet_key = vault_unlock(master_password)
    if not fernet_key:
        return HTMLResponse('<div class="alert alert-danger">Senha mestra incorreta.</div>', status_code=400)
    request.session[_SESSION_VAULT_KEY] = base64.b64encode(fernet_key).decode()
    return HTMLResponse('<div class="alert alert-success">Cofre desbloqueado!</div>')


@app.post("/api/vault/change-password", response_class=HTMLResponse)
async def vault_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    user = get_user(request)
    if not user:
        return HTMLResponse('<div class="alert alert-danger">Não autenticado.</div>', status_code=401)
    if not vault_is_configured():
        return HTMLResponse('<div class="alert alert-danger">Cofre não configurado.</div>', status_code=400)
    old_key = vault_unlock(current_password)
    if not old_key:
        return HTMLResponse('<div class="alert alert-danger">Senha atual do cofre incorreta.</div>', status_code=400)
    if len(new_password) < 6:
        return HTMLResponse('<div class="alert alert-danger">A nova senha deve ter pelo menos 6 caracteres.</div>', status_code=400)
    if new_password != confirm_password:
        return HTMLResponse('<div class="alert alert-danger">As senhas não coincidem.</div>', status_code=400)

    # Gera nova chave e re-criptografa todas as senhas de câmeras
    new_salt = os.urandom(16)
    new_key = _derive_fernet_key(new_password, new_salt)
    from cryptography.fernet import Fernet as _Fernet
    new_check = _Fernet(new_key).encrypt(b"nexus-vault-ok")
    AppConfig.insert_many([
        {AppConfig.key: _VAULT_SALT_KEY,  AppConfig.value: base64.b64encode(new_salt).decode()},
        {AppConfig.key: _VAULT_CHECK_KEY, AppConfig.value: new_check.decode()},
    ]).on_conflict_replace().execute()
    for cam in Camera.select().where(Camera.password.is_null(False)):
        if cam.password and cam.password.startswith(ENC_PREFIX):
            plain = decrypt_password(cam.password, old_key)
            cam.password = encrypt_password(plain, new_key)
            cam.save()
    # Atualiza a chave na sessão
    request.session[_SESSION_VAULT_KEY] = base64.b64encode(new_key).decode()
    return HTMLResponse('<div class="alert alert-success">Senha do cofre alterada com sucesso. Todas as senhas foram re-criptografadas.</div>')


# ── Admin Users ───────────────────────────────────────────────────────────────
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": user,
    })


@app.get("/partials/admin/users", response_class=HTMLResponse)
async def admin_users_partial(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("", status_code=401)
    users = list(User.select().order_by(User.username))
    return templates.TemplateResponse("partials/user_table.html", {
        "request": request,
        "users": users,
        "current_user": user,
    })


@app.post("/api/admin/users", response_class=HTMLResponse)
async def admin_create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("VIEWER"),
):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("", status_code=401)
    try:
        create_user(username=username, plain_password=password, role=role)
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger px-2 py-1 small mb-2'>Erro: {e}</div>")
    return await admin_users_partial(request)


@app.post("/api/admin/users/{user_id}/toggle", response_class=HTMLResponse)
async def admin_toggle_user(request: Request, user_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("", status_code=401)
    
    target = User.get_or_none(User.id == user_id)
    if target and target.username != user.username:
        target.is_active = not target.is_active
        target.save()
    
    return await admin_users_partial(request)


# ── NVR / Gravadores ──────────────────────────────────────────────────────────
@app.get("/nvr", response_class=HTMLResponse)
async def nvr_page(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    nvrs = list(Camera.select().where(Camera.is_nvr == True).order_by(Camera.name))
    orphan_cameras = list(
        Camera.select()
        .where(Camera.is_nvr == False, Camera.parent.is_null(True))
        .order_by(Camera.ip_address)
    )
    orphan_cameras_json = [
        {"id": c.id, "ip_address": c.ip_address, "name": c.name or ""}
        for c in orphan_cameras
    ]
    return templates.TemplateResponse("nvr.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
        "nvrs": nvrs,
        "orphan_cameras": orphan_cameras_json,
    })


@app.post("/api/nvr/{nvr_id}/link", response_class=HTMLResponse)
async def nvr_link_camera(request: Request, nvr_id: int, camera_id: str = Form(...)):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    nvr = Camera.get_or_none(Camera.id == nvr_id, Camera.is_nvr == True)
    cam = Camera.get_or_none(Camera.id == int(camera_id))
    if nvr and cam:
        cam.parent = nvr
        cam.save()
    return RedirectResponse("/nvr", status_code=303)


@app.post("/api/nvr/unlink/{camera_id}", response_class=HTMLResponse)
async def nvr_unlink_camera(request: Request, camera_id: int):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)
    cam = Camera.get_or_none(Camera.id == camera_id)
    if cam:
        cam.parent = None
        cam.save()
    return RedirectResponse("/nvr", status_code=303)


# ── Backup / Restore ──────────────────────────────────────────────────────────
@app.get("/admin/backup", response_class=HTMLResponse)
async def backup_page(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return RedirectResponse("/login")
    return templates.TemplateResponse("admin_backup.html", {
        "request": request,
        "user": user,
        "is_admin": True,
    })


@app.get("/api/backup")
async def download_backup(request: Request):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        raise HTTPException(status_code=403)

    tmp_path = str(DB_PATH) + ".backup_tmp"
    try:
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        dst.close()
        src.close()
        data = DB_PATH.parent.joinpath(DB_PATH.name + ".backup_tmp").read_bytes()
    finally:
        import os
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    filename = f"nexus_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/restore", response_class=HTMLResponse)
async def restore_backup(request: Request, file: UploadFile = File(...)):
    user = get_user(request)
    if not user or user.role != "ADMIN":
        return HTMLResponse("<div class='alert alert-danger'>Sem permissão</div>", status_code=403)

    data = await file.read()
    try:
        restore_database(data)
    except ValueError as e:
        return HTMLResponse(f"<div class='alert alert-danger'><b>Arquivo inválido:</b> {e}</div>")
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'><b>Erro ao restaurar:</b> {e}</div>")

    return HTMLResponse(
        "<div class='alert alert-success'>"
        "<b>Banco restaurado com sucesso!</b> "
        "<a href='/cameras' class='alert-link'>Ir para Câmeras</a>"
        "</div>"
    )


# ── Entrypoint ────────────────────────────────────────────────────────────────
def _find_free_port(start: int = 8000) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return start


if __name__ == "__main__":
    import os

    port = int(os.environ.get("NEXUS_PORT", 0)) or _find_free_port()

    def _open_browser():
        time.sleep(2.0)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()
    print(f"[Nexus Scan] Servidor em http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
