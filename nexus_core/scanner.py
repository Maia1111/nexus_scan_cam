from __future__ import annotations

import ctypes
import ipaddress
import os
import re
import socket
import struct
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable


SCAN_PORTS = (80, 443, 554, 8080, 8000, 34567, 37777, 8554, 37778, 1935, 2020, 9000, 8888)
MAX_WORKERS = 50


CAMERA_OUI_TABLE = {
    # Hikvision
    "00:1B:79": "Hikvision",
    "3C:EF:8C": "Hikvision",
    "BC:51:FE": "Hikvision",
    "1C:E0:4F": "Hikvision",
    "C8:2E:47": "Hikvision",
    "A4:14:37": "Hikvision",
    "48:EA:63": "Hikvision",
    "8C:E7:48": "Hikvision",
    "CC:73:14": "Hikvision",
    "1C:39:29": "Hikvision",
    "C4:82:E1": "Hikvision",
    "44:19:B6": "Hikvision",
    # Dahua
    "FC:D7:33": "Dahua",
    "A0:BD:1D": "Dahua",
    "38:AF:29": "Dahua",
    "BC:1C:81": "Dahua",
    "4C:11:BF": "Dahua",
    "9C:8E:CD": "Dahua",
    "90:48:46": "Dahua",
    "BC:32:B2": "Dahua",
    # Intelbras
    "E4:24:6C": "Intelbras",
    "90:02:A9": "Intelbras",
    "FC:5B:39": "Intelbras",
    "18:D6:C7": "Intelbras",
    "D4:6E:0E": "Intelbras",
    "F8:01:B4": "Intelbras",
    "60:56:EE": "Intelbras",
    "82:96:E8": "Intelbras",
    "D8:BE:65": "Intelbras",
    "9C:84:B6": "Intelbras",
    # Axis
    "EC:71:DB": "Axis",
    "00:40:8C": "Axis",
    "00:1A:79": "Axis",
    "3C:A0:67": "Axis",
    # Hanwha / Samsung Techwin
    "10:7B:44": "Hanwha",
    "00:12:31": "Samsung Techwin",
    # Vivotek
    "00:23:63": "Vivotek",
    # XM / Genérica chinesa
    "AC:CC:8E": "XM",
    # Reolink
    "C4:D9:87": "Reolink",
    # TP-Link / Tapo
    "98:D8:63": "TP-Link",
    "50:C7:BF": "TP-Link",
    "00:0A:EB": "TP-Link",
    "C0:06:C3": "TP-Link",
    "B0:A7:B9": "TP-Link",
    "50:8B:B9": "TP-Link",
}

INTELBRAS_HINT_PORTS = {37777}

# Detecção de marca por porta quando MAC não identifica o fabricante
PORT_BRAND_HINTS = {
    8000:  "Hikvision",
    37777: "Intelbras / Dahua",
    37778: "Dahua",
    34567: "Intelbras / Dahua",
}


@dataclass(slots=True)
class DeviceProbeResult:
    ip: str
    mac: str | None
    brand: str
    open_ports: list[int]
    score: int
    is_nvr: bool = False


class NetworkScanner:
    def __init__(
        self,
        timeout: float = 0.4,
        max_workers: int = MAX_WORKERS,
        ports: Iterable[int] = SCAN_PORTS,
        on_progress: Callable[[int, int], None] | None = None,
        on_result: Callable[[DeviceProbeResult], None] | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_workers = min(MAX_WORKERS, max(1, max_workers))
        self.ports = tuple(dict.fromkeys(ports))
        self.on_progress = on_progress
        self.on_result = on_result

    @staticmethod
    def get_all_networks() -> list[str]:
        """Detecta todas as redes IPv4 ativas em todas as interfaces de rede."""
        networks = set()
        
        # Tenta usar o comando 'ip' no Linux (mais preciso para CIDR)
        if os.name != "nt":
            try:
                import subprocess
                output = subprocess.check_output(["ip", "-4", "addr", "show"], text=True)
                # Procura por padrões como 'inet 192.168.1.5/24'
                matches = re.findall(r"inet\s+(\d+\.\d+\.\d+\.\d+/\d+)", output)
                for match in matches:
                    # Ignora loopback
                    if not match.startswith("127."):
                        try:
                            net = ipaddress.ip_network(match, strict=False)
                            networks.add(str(net))
                        except ValueError:
                            continue
            except Exception:
                pass

        # Fallback usando sockets (funciona em Windows/Linux)
        try:
            # Obtém todas as interfaces através do hostname
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    # Assume /24 como padrão quando não temos o CIDR exato no fallback
                    parts = ip.split(".")
                    networks.add(f"{parts[0]}.{parts[1]}.{parts[2]}.0/24")
        except Exception:
            pass

        # Se nada for encontrado, retorna o padrão
        if not networks:
            return ["192.168.1.0/24"]
            
        return sorted(list(networks))

    @staticmethod
    def get_local_network() -> str:
        """Retorna a rede principal detectada."""
        all_nets = NetworkScanner.get_all_networks()
        return all_nets[0] if all_nets else "192.168.1.0/24"

    @staticmethod
    def _build_ws_discovery_probe() -> bytes:
        message_id = f"uuid:{uuid.uuid4()}"
        payload = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<e:Envelope xmlns:e=\"http://www.w3.org/2003/05/soap-envelope\"
            xmlns:w=\"http://schemas.xmlsoap.org/ws/2004/08/addressing\"
            xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\"
            xmlns:dn=\"http://www.onvif.org/ver10/network/wsdl\">
  <e:Header>
    <w:MessageID>{message_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>"""
        return payload.encode("utf-8")

    @staticmethod
    def discover_onvif_devices(timeout: float = 1.8, retries: int = 2) -> set[str]:
        discovered_ips: set[str] = set()
        multicast_target = ("239.255.255.250", 3702)
        probe = NetworkScanner._build_ws_discovery_probe()
        ip_pattern = re.compile(r"https?://(\d+\.\d+\.\d+\.\d+)")

        for _ in range(max(1, retries)):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(timeout)

            try:
                sock.sendto(probe, multicast_target)
                start = time.time()
                while time.time() - start < timeout:
                    try:
                        data, addr = sock.recvfrom(16384)
                        response_text = data.decode("utf-8", errors="ignore")
                        extracted = ip_pattern.findall(response_text)

                        if extracted:
                            discovered_ips.update(extracted)
                        else:
                            discovered_ips.add(addr[0])
                    except socket.timeout:
                        break
                    except OSError:
                        break
            except OSError:
                pass
            finally:
                sock.close()

        return discovered_ips

    @staticmethod
    def discover_onvif_unicast(hosts: list[str], timeout: float = 0.25) -> set[str]:
        discovered_ips: set[str] = set()
        probe = NetworkScanner._build_ws_discovery_probe()

        for host in hosts:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(timeout)
            try:
                sock.sendto(probe, (host, 3702))
                _data, addr = sock.recvfrom(8192)
                discovered_ips.add(addr[0])
            except OSError:
                continue
            finally:
                sock.close()

        return discovered_ips

    @staticmethod
    def _normalize_mac(raw_mac: str | None) -> str | None:
        if not raw_mac:
            return None
        cleaned = raw_mac.replace("-", ":").replace(".", "").upper()
        if ":" in cleaned:
            parts = [part.zfill(2) for part in cleaned.split(":") if part]
            return ":".join(parts[:6]) if len(parts) >= 6 else None
        if len(cleaned) >= 12:
            return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
        return None

    @staticmethod
    def detect_brand(mac: str | None) -> str:
        normalized = NetworkScanner._normalize_mac(mac)
        if not normalized:
            return "Desconhecida"

        oui = ":".join(normalized.split(":")[:3])
        return CAMERA_OUI_TABLE.get(oui, "Desconhecida")

    @staticmethod
    def _parse_arp_linux() -> dict[str, str]:
        arp_map: dict[str, str] = {}
        try:
            with open("/proc/net/arp", "r", encoding="utf-8", errors="ignore") as arp_file:
                lines = arp_file.readlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    ip_addr = parts[0]
                    mac_addr = parts[3]
                    if mac_addr != "00:00:00:00:00:00":
                        arp_map[ip_addr] = mac_addr.upper()
        except OSError:
            return {}
        return arp_map

    @staticmethod
    def _parse_arp_windows() -> dict[str, str]:
        arp_map: dict[str, str] = {}

        class MIB_IPNETROW(ctypes.Structure):
            _fields_ = [
                ("dwIndex", ctypes.c_ulong),
                ("dwPhysAddrLen", ctypes.c_ulong),
                ("bPhysAddr", ctypes.c_ubyte * 8),
                ("dwAddr", ctypes.c_ulong),
                ("dwType", ctypes.c_ulong),
            ]

        ERROR_INSUFFICIENT_BUFFER = 122
        size = ctypes.c_ulong(0)
        iphlpapi = ctypes.windll.Iphlpapi
        result = iphlpapi.GetIpNetTable(None, ctypes.byref(size), False)

        if result not in (0, ERROR_INSUFFICIENT_BUFFER):
            return arp_map

        buffer = ctypes.create_string_buffer(size.value)
        result = iphlpapi.GetIpNetTable(buffer, ctypes.byref(size), False)
        if result != 0:
            return arp_map

        entries = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ulong)).contents.value
        offset = ctypes.sizeof(ctypes.c_ulong)
        row_size = ctypes.sizeof(MIB_IPNETROW)

        for index in range(entries):
            row_ptr = ctypes.cast(
                ctypes.addressof(buffer) + offset + (index * row_size),
                ctypes.POINTER(MIB_IPNETROW),
            )
            row = row_ptr.contents

            if row.dwPhysAddrLen < 6:
                continue

            ip_addr = socket.inet_ntoa(struct.pack("<L", row.dwAddr))
            mac_bytes = bytes(row.bPhysAddr[: row.dwPhysAddrLen])
            mac_addr = ":".join(f"{byte:02X}" for byte in mac_bytes[:6])
            arp_map[ip_addr] = mac_addr

        return arp_map

    @staticmethod
    def parse_arp_table() -> dict[str, str]:
        if os.name == "nt":
            try:
                return NetworkScanner._parse_arp_windows()
            except Exception:
                return {}
        return NetworkScanner._parse_arp_linux()

    def _probe_port(self, ip_addr: str, port: int) -> bool:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(self.timeout)
        try:
            return conn.connect_ex((ip_addr, port)) == 0
        except OSError:
            return False
        finally:
            conn.close()

    def _score_device(self, open_ports: list[int], brand: str) -> tuple[int, bool]:
        score = 0
        is_nvr = False

        # Portas típicas de NVR/DVR
        nvr_ports = {8000, 37777, 34567, 37778}
        open_nvr_ports = [p for p in open_ports if p in nvr_ports]
        
        # Se tiver mais de uma porta de gerência aberta, é muito provável que seja um gravador
        if len(open_nvr_ports) >= 2:
            is_nvr = True
            score += 90
        elif any(p in open_ports for p in (8000, 37777)):
             # Um gravador Hikvision/Intelbras muitas vezes é identificado por uma única porta forte
             # Mas vamos ser conservadores e checar a marca se disponível
             if brand in ("Hikvision", "Intelbras", "Dahua"):
                 is_nvr = True
                 score += 85

        if 554 in open_ports or 8554 in open_ports:
            score += 80
        elif 80 in open_ports or 8080 in open_ports:
            score += 10

        if any(port in open_ports for port in (37777, 8000, 34567, 37778, 1935, 2020)):
            score += 20

        if brand != "Desconhecida":
            score += 10

        return min(score, 100), is_nvr

    def _probe_host(
        self,
        ip_addr: str,
        arp_map: dict[str, str],
        onvif_hint: bool = False,
    ) -> DeviceProbeResult | None:
        try:
            open_ports = [port for port in self.ports if self._probe_port(ip_addr, port)]

            if not open_ports and not onvif_hint:
                return None

            mac = arp_map.get(ip_addr)
            brand = self.detect_brand(mac)
            if brand == "Desconhecida":
                for port, hint_brand in PORT_BRAND_HINTS.items():
                    if port in open_ports:
                        brand = hint_brand
                        break
            score, is_nvr = self._score_device(open_ports, brand)

            if onvif_hint:
                score = max(score, 90)

            if score < 20:
                return None

            return DeviceProbeResult(
                ip=ip_addr,
                mac=mac,
                brand=brand,
                open_ports=open_ports,
                score=score,
                is_nvr=is_nvr,
            )
        except Exception:
            return None

    def scan_network(
        self,
        network_cidr: str,
        stop_event: threading.Event | None = None,
        enable_onvif_unicast: bool = False,
    ) -> list[DeviceProbeResult]:
        try:
            net = ipaddress.ip_network(network_cidr, strict=False)
        except ValueError:
            return []

        hosts = [str(host) for host in net.hosts()]
        if not hosts:
            return []

        arp_map = self.parse_arp_table()
        onvif_devices = self.discover_onvif_devices()
        if enable_onvif_unicast:
            onvif_devices.update(self.discover_onvif_unicast(hosts))
        network_onvif_ips: set[str] = set()
        for ip_addr in onvif_devices:
            try:
                if ipaddress.ip_address(ip_addr) in net:
                    network_onvif_ips.add(ip_addr)
            except ValueError:
                continue
        total_hosts = len(hosts)
        scanned_hosts = 0
        results: list[DeviceProbeResult] = []
        result_ips: set[str] = set()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._probe_host, host, arp_map, host in network_onvif_ips): host
                for host in hosts
            }

            for future in as_completed(futures):
                if stop_event and stop_event.is_set():
                    break

                scanned_hosts += 1
                try:
                    result = future.result()
                except Exception:
                    result = None

                if result is not None:
                    if result.ip in result_ips:
                        continue
                    results.append(result)
                    result_ips.add(result.ip)
                    if self.on_result:
                        try:
                            self.on_result(result)
                        except Exception:
                            pass

                if self.on_progress:
                    try:
                        self.on_progress(scanned_hosts, total_hosts)
                    except Exception:
                        pass

        for ip_addr in sorted(network_onvif_ips):
            if ip_addr in result_ips:
                continue

            result = self._probe_host(ip_addr, arp_map, onvif_hint=True)
            if result is None:
                continue

            results.append(result)
            result_ips.add(result.ip)
            if self.on_result:
                try:
                    self.on_result(result)
                except Exception:
                    pass

        return sorted(results, key=lambda item: item.score, reverse=True)


class CameraMonitor(threading.Thread):
    def __init__(
        self,
        camera_provider: Callable[[], list[tuple[str, tuple[int, ...]]]],
        status_callback: Callable[[str, bool, float | None], None],
        interval_seconds: int = 15,
        timeout: float = 1.0,
    ) -> None:
        super().__init__(daemon=True)
        self.camera_provider = camera_provider
        self.status_callback = status_callback
        self.interval_seconds = max(5, interval_seconds)
        self.timeout = timeout
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def _tcp_ping(self, ip_addr: str, ports: tuple[int, ...]) -> tuple[bool, float | None]:
        for port in ports:
            start = time.perf_counter()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                if sock.connect_ex((ip_addr, port)) == 0:
                    latency = (time.perf_counter() - start) * 1000
                    return True, round(latency, 2)
            except OSError:
                continue
            finally:
                sock.close()
        return False, None

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cameras = self.camera_provider()
                for ip_addr, ports in cameras:
                    if self._stop_event.is_set():
                        break
                    online, latency_ms = self._tcp_ping(ip_addr, ports)
                    try:
                        self.status_callback(ip_addr, online, latency_ms)
                    except Exception:
                        pass
            except Exception:
                pass

            for _ in range(self.interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
