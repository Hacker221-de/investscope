"""Opt-in protection for sensitive localhost mutations, independent of CORS middleware."""

import re
from collections.abc import Sequence
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


def _loopback_authority(authority: str) -> bool:
    # Restrict authority syntax before urlsplit, which tolerates some invalid
    # inputs (including stripped controls and text following an IPv6 bracket).
    if not re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?", authority, re.I):
        return False
    try:
        parsed = urlsplit("//" + authority)
        port = parsed.port
    except ValueError:
        return False
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"} and (
        port is None or 0 <= port <= 65535
    )


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
    match = re.fullmatch(r"https?://([^/?#]+)", origin)
    if match is None or not _loopback_authority(match[1]) or origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="Origin is not an allowed loopback origin")
