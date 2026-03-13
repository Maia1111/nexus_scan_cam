from __future__ import annotations

import asyncio
import json
import socket
import time
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import httpx
import uvicorn
from weasyprint import HTML as WeasyHTML
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from models import (
    Camera,
    CameraGroup,
    User,
    create_user,
    ensure_default_camera_group,
    has_any_user,
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
templates = Jinja2Templates(directory="templates")
templates.env.filters["tojson"] = json.dumps


# ── Auth helpers ──────────────────────────────────────────────────────────────
def get_user(request: Request) -> Optional[User]:
    username = request.session.get("username")
    if not username:
        return None
    return User.get_or_none(User.username == username, User.is_active == True)


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
async def page_scanner(request: Request):
    user = get_user(request)
    if not user:
        return RedirectResponse("/login")
    
    networks = NetworkScanner.get_all_networks()
    default_net = networks[0] if networks else "192.168.1.0/24"
    
    return templates.TemplateResponse("scanner.html", {
        "request": request,
        "user": user,
        "is_admin": user.role == "ADMIN",
        "default_network": default_net,
        "detected_networks": networks,
        "scan_running": _scan_running,
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
    name: str = Form(""),
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
    )
    label = name.strip() or ip_address
    return HTMLResponse(f"<span class='badge bg-success'>✓ {label}</span>")


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
async def _tcp_ping_multi(ip: str, port: int, count: int = 4, timeout: float = 1.5) -> dict:
    """Pinga via TCP `count` vezes e retorna métricas de latência/perda."""
    loop = asyncio.get_running_loop()

    def _connect() -> float | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            return (time.perf_counter() - t0) * 1000 if sock.connect_ex((ip, port)) == 0 else None
        except OSError:
            return None
        finally:
            sock.close()

    samples: list[float | None] = []
    for _ in range(count):
        samples.append(await loop.run_in_executor(None, _connect))

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

    # Verificações estáticas
    for cam in cameras:
        if not cam.is_online and cam.last_seen_at:
            issues.append({
                "severity": "warning", "icon": "wifi-off",
                "type": "offline", "title": "Câmera offline",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — última resposta em {cam.last_seen_at.strftime('%d/%m/%Y %H:%M')}",
                "camera": cam,
            })
    for cam in cameras:
        if cam.last_seen_at is None:
            issues.append({
                "severity": "info", "icon": "question-circle",
                "type": "never_seen", "title": "Nunca respondeu",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — cadastrada mas nunca foi vista online",
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
                "camera": cams[0],
            })
    for cam in cameras:
        if not cam.username:
            issues.append({
                "severity": "info", "icon": "key",
                "type": "no_credentials", "title": "Sem credenciais",
                "detail": f"{cam.name or cam.ip_address} ({cam.ip_address}) — sem usuário/senha cadastrado",
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
                        f"(cadastrado como {cam.ip_address}). A câmera provavelmente usa DHCP — "
                        f"configure um IP fixo no roteador ou na câmera para evitar perda de acesso."
                    ),
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

        ping_results = await asyncio.gather(
            *[_tcp_ping_multi(cam.ip_address, _get_port(cam)) for cam in cameras]
        )
        for cam, p in zip(cameras, ping_results):
            label = cam.name or cam.ip_address
            if cam.is_online and not p["reachable"]:
                issues.append({
                    "severity": "danger", "icon": "slash-circle",
                    "type": "frozen", "title": "Câmera não responde (possível travamento)",
                    "detail": f"{label} ({cam.ip_address}) marcada como online mas não respondeu a nenhum dos 4 pings TCP.",
                    "camera": cam,
                })
            elif p["reachable"]:
                avg, jitter, loss = p["avg_ms"], p["jitter_ms"], p["loss_pct"]
                if avg > 300:
                    issues.append({"severity": "danger", "icon": "speedometer", "type": "high_latency",
                        "title": "Latência crítica — possível loop de rede",
                        "detail": f"{label}: latência média {avg:.0f}ms (>300ms indica loop ou gargalo grave).", "camera": cam})
                elif avg > 80:
                    issues.append({"severity": "warning", "icon": "speedometer2", "type": "high_latency",
                        "title": "Latência alta",
                        "detail": f"{label}: latência {avg:.0f}ms (esperado <20ms em LAN).", "camera": cam})
                if jitter > 100:
                    issues.append({"severity": "danger", "icon": "graph-up-arrow", "type": "jitter",
                        "title": "Instabilidade grave (jitter alto)",
                        "detail": f"{label}: jitter {jitter:.0f}ms — provável loop de rede ou broadcast storm.", "camera": cam})
                elif jitter > 40:
                    issues.append({"severity": "warning", "icon": "graph-up", "type": "jitter",
                        "title": "Conexão instável",
                        "detail": f"{label}: jitter {jitter:.0f}ms acima do normal.", "camera": cam})
                if loss >= 50:
                    issues.append({"severity": "danger", "icon": "reception-0", "type": "packet_loss",
                        "title": f"Perda de pacotes grave: {loss:.0f}%",
                        "detail": f"{label}: {loss:.0f}% dos pacotes TCP perdidos.", "camera": cam})
                elif loss > 0:
                    issues.append({"severity": "warning", "icon": "reception-2", "type": "packet_loss",
                        "title": f"Perda de pacotes: {loss:.0f}%",
                        "detail": f"{label}: {loss:.0f}% dos pacotes perdidos.", "camera": cam})

            network_stats.append({
                "cam": cam, "reachable": p["reachable"],
                "avg_ms": p["avg_ms"], "jitter_ms": p["jitter_ms"], "loss_pct": p["loss_pct"],
            })

    return {
        "issues": issues,
        "network_stats": network_stats,
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
        lambda: WeasyHTML(string=html_content).write_pdf()
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
        lambda: WeasyHTML(string=html_content).write_pdf()
    )

    filename = f"relatorio_agrupado_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Camera snapshot viewer ─────────────────────────────────────────────────────
_SNAPSHOT_URLS = [
    "http://{ip}/snapshot.jpg",
    "http://{ip}/snap.jpg",
    "http://{ip}/tmpfs/snap.jpg",
    "http://{ip}/cgi-bin/snapshot.cgi",
    "http://{ip}/onvif/snapshot",
    "http://{ip}:8080/snapshot.jpg",
    "http://{ip}/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2",
    "http://{ip}/ISAPI/Streaming/channels/101/picture",
    "http://{ip}/cgi-bin/mjpg/video.cgi?channel=0&subtype=1",
]


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

    u = username or cam.username or ""
    p = password or cam.password or ""
    auth = (u, p) if u else None

    async with httpx.AsyncClient(timeout=5.0, verify=False, follow_redirects=True) as client:
        for url_tpl in _SNAPSHOT_URLS:
            url = url_tpl.format(ip=cam.ip_address)
            try:
                resp = await client.get(url, auth=auth)
                ct = resp.headers.get("content-type", "")
                if resp.status_code == 200 and "image" in ct:
                    return Response(content=resp.content, media_type=ct)
            except Exception:
                continue

    raise HTTPException(status_code=404, detail="Snapshot não disponível para esta câmera")


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


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    def _open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
