"""Shared authority parsing and stricter local-only SEC upload protection."""

import re
from collections.abc import Sequence
from ipaddress import IPv4Address, IPv6Address
from typing import NamedTuple

from fastapi import HTTPException, Request


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class Authority(NamedTuple):
    hostname: str
    port: int | None


def parse_authority(authority: str) -> Authority | None:
    """Strict Host/Origin authority; no DNS, URL coercion or forwarded headers."""
    match = re.fullmatch(
        r"(?P<host>\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(?::(?P<port>[0-9]+))?",
        authority,
    )
    if match is None:
        return None
    hostname = match["host"].lower()
    port_text = match["port"]
    port = None
    if port_text is not None:
        significant = port_text.lstrip("0") or "0"
        if len(significant) > 5 or int(significant) > 65535:
            return None
        port = int(significant)
    try:
        if hostname.startswith("["):
            hostname = hostname[1:-1]
            IPv6Address(hostname)
        elif re.fullmatch(r"[0-9.]+", hostname):
            IPv4Address(hostname)
        elif len(hostname) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in hostname.split(".")
        ):
            return None
    except ValueError:
        return None
    return Authority(hostname, port)


def validate_trusted_hostname(value: str) -> str:
    # Config IPv6 is unbracketed; HTTP authorities require brackets. Reuse the
    # same parser rather than maintaining a second hostname validation grammar.
    if not value or value != value.strip() or "[" in value or "]" in value:
        raise ValueError("trusted_hosts entries must be bare hostnames or IP addresses")
    authority = parse_authority(f"[{value}]" if ":" in value else value)
    if authority is None or authority.port is not None:
        raise ValueError("trusted_hosts entries must be bare hostnames or IP addresses")
    return authority.hostname


def parse_origin(origin: str) -> Authority | None:
    # Origin allowlist comparison remains exact; never normalize the origin URL.
    match = re.fullmatch(r"https?://([^/?#]+)", origin)
    return parse_authority(match[1]) if match else None


def _loopback_authority(authority: str) -> bool:
    parsed = parse_authority(authority)
    return parsed is not None and parsed.hostname in LOOPBACK_HOSTS


def require_local_request(request: Request, *, allowed_origins: Sequence[str]) -> None:
    hosts = request.headers.getlist("host")
    if len(hosts) != 1 or not _loopback_authority(hosts[0]):
        raise HTTPException(status_code=403, detail="A valid loopback Host is required")

    origins = request.headers.getlist("origin")
    if not origins:
        return  # Trusted local non-browser clients still require the Host check.
    if len(origins) != 1:
        raise HTTPException(status_code=403, detail="A single allowed loopback Origin is required")
    origin = origins[0]
    parsed = parse_origin(origin)
    if parsed is None or parsed.hostname not in LOOPBACK_HOSTS or origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="Origin is not an allowed loopback origin")
