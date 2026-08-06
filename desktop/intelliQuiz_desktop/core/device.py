from __future__ import annotations

import hashlib
import platform
import socket
import uuid


def device_fingerprint() -> str:
    raw = f"{platform.node()}|{platform.system()}|{platform.machine()}|{uuid.getnode()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def discover_lan_ip() -> str:
    """Best-effort LAN IPv4 for phone QR URLs (not 127.0.0.1)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"
