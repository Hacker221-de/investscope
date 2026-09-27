"""Global pre-body Host/Origin boundary. CORS alone is not CSRF protection."""

from dataclasses import dataclass

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.local_request_security import LOOPBACK_HOSTS, parse_authority, parse_origin


@dataclass(frozen=True, slots=True)
class RequestSecurityConfig:
    desktop: bool
    trusted_hosts: frozenset[str]
    cors_origins: frozenset[str]

    @classmethod
    def from_settings(cls, settings: Settings) -> "RequestSecurityConfig":
        return cls(
            desktop=settings.mode == "desktop",
            trusted_hosts=frozenset(settings.trusted_hosts),
            cors_origins=frozenset(settings.cors_origins),
        )


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.config = RequestSecurityConfig.from_settings(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        hosts = headers.getlist("host")
        host = parse_authority(hosts[0]) if len(hosts) == 1 else None
        host_allowed = host is not None and (
            host.hostname in LOOPBACK_HOSTS
            or (not self.config.desktop and host.hostname in self.config.trusted_hosts)
        )
        if not host_allowed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008, "reason": "Forbidden request host"})
            else:
                await JSONResponse({"detail": "Forbidden request host"}, status_code=403)(scope, receive, send)
            return

        if scope["type"] == "http" and scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origins = headers.getlist("origin")
            if origins:
                origin = parse_origin(origins[0]) if len(origins) == 1 else None
                if (
                    origin is None
                    or origins[0] not in self.config.cors_origins
                    or (self.config.desktop and origin.hostname not in LOOPBACK_HOSTS)
                ):
                    await JSONResponse({"detail": "Forbidden request origin"}, status_code=403)(scope, receive, send)
                    return

        # No receive(), body access, dependencies or provider construction above.
        # Forwarded/X-Forwarded-* headers never participate in either decision.
        await self.app(scope, receive, send)
