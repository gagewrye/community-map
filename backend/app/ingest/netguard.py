"""SSRF guard: only allow fetching URLs whose host resolves to public IP addresses."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


def is_public_url(url: str, resolve=socket.getaddrinfo) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = resolve(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    addrs = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos}
    return bool(addrs) and all(a.is_global for a in addrs)
