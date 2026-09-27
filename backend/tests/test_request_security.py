import asyncio
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.core.config import Settings
from app.core.local_request_security import parse_authority
from app.core.request_security import RequestSecurityMiddleware
from app.main import create_app

LOCAL_ORIGIN = "http://127.0.0.1:3200"
REMOTE_ORIGIN = "https://app.example.test"


def security_settings(**overrides):
    values = dict(
        _env_file=None, mode="server", trusted_hosts=["localhost", "127.0.0.1", "::1"],
        cors_origins=[LOCAL_ORIGIN],
    )
    values.update(overrides)
    return Settings(**values)


def call_http(app, *, method="GET", path="/probe", headers=None, body=b"", query=b""):
    """Actual ASGI boundary: count EVERY receive; no TestClient Host injection."""
    received = 0
    messages = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": query, "root_path": "", "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
        "headers": [(key.lower().encode(), value.encode("latin-1")) for key, value in (
            headers if headers is not None else [("host", "127.0.0.1")]
        )],
    }
    async def receive():
        nonlocal received
        received += 1
        if received == 1:
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return start["status"], response_body, received, dict(start["headers"])


def policy_app(settings):
    application = FastAPI()
    application.state.endpoint_calls = 0
    @application.api_route("/probe", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "CUSTOM"])
    async def probe(request: Request):
        application.state.endpoint_calls += 1
        await request.body()
        return Response(status_code=204)
    application.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["*"],
    )
    application.add_middleware(RequestSecurityMiddleware, settings=settings)
    return application


@pytest.mark.parametrize(("authority", "hostname", "port"), [
    ("localhost", "localhost", None), ("LOCALHOST:18000", "localhost", 18000),
    ("127.0.0.1:8000", "127.0.0.1", 8000), ("[::1]", "::1", None),
    ("[::1]:65535", "::1", 65535), ("api.example.com", "api.example.com", None),
    ("API.Example.com:443", "api.example.com", 443),
    ("[2001:db8::1]:443", "2001:db8::1", 443),
])
def test_shared_authority_parser(authority, hostname, port):
    assert parse_authority(authority) == (hostname, port)


@pytest.mark.parametrize("authority", [
    "", " localhost", "localhost ", "local\thost", "localhost\n", "localhost:",
    "localhost:65536", "localhost:-1", "localhost:+1", "localhost:abc", "localhost:1:2",
    "user@localhost", "localhost/path", "localhost?x", "localhost#x", "localhost\\x",
    "::1", "[::1", "[::1]evil", "[::1%lo0]", "http://localhost", "example..com",
    "example.com.", "-example.com", "example-.com", "exa_mple.com", "127.1", "999.0.0.1",
    "[gg::1]", "localhost:999999999999999999999999999999999",
])
def test_malformed_authority_rejected(authority):
    assert parse_authority(authority) is None


@pytest.mark.parametrize("mode", ["server", "desktop"])
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "LOCALHOST:8000"])
def test_loopback_host_allowed(mode, host):
    result = call_http(policy_app(security_settings(mode=mode)), headers=[("host", host)])
    assert result[0] == 204


@pytest.mark.parametrize("headers", [
    [], [("host", "evil.example")], [("host", "testserver")], [("host", "localhost:bad")],
    [("host", "localhost"), ("host", "127.0.0.1")], [("host", "localhost/secret")],
])
@pytest.mark.parametrize("method", ["GET", "POST", "HEAD", "OPTIONS"])
def test_bad_host_precedes_body_and_endpoint(headers, method):
    application = policy_app(security_settings())
    status, body, received, response_headers = call_http(application, method=method, headers=headers, body=b"unparsed")
    assert status == 403 and json.loads(body) == {"detail": "Forbidden request host"}
    assert received == 0 and application.state.endpoint_calls == 0
    assert b"access-control-allow-origin" not in response_headers


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "CUSTOM", "TRACE", "CONNECT"])
def test_all_non_safe_methods_protected_before_routing(method):
    application = policy_app(security_settings())
    status, body, received, _ = call_http(application, method=method, headers=[
        ("host", "localhost"), ("origin", "https://evil.example"),
    ], body=b'{"never":"read"}')
    assert status == 403 and json.loads(body) == {"detail": "Forbidden request origin"}
    assert received == 0 and application.state.endpoint_calls == 0


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_do_not_require_valid_origin(method):
    status, _, _, _ = call_http(policy_app(security_settings()), method=method, headers=[
        ("host", "localhost"), ("origin", "null"), ("origin", "https://evil.example"),
    ])
    assert status == 204


@pytest.mark.parametrize("mode", ["server", "desktop"])
@pytest.mark.parametrize("origin", [None, LOCAL_ORIGIN])
def test_missing_or_allowed_origin_passes(mode, origin):
    headers = [("host", "127.0.0.1")]
    if origin is not None:
        headers.append(("origin", origin))
    result = call_http(policy_app(security_settings(mode=mode)), method="POST", headers=headers, body=b"data")
    assert result[0] == 204 and result[2] == 1


@pytest.mark.parametrize("origin", [
    "null", "", "https://app.example.test/", "http://user@localhost", "http://localhost/path",
    "http://localhost?x", "http://localhost#x", "file://localhost", "http://localhost:bad",
    "http://localhost\n", "http://localhost http://other", "https://[::1]junk",
])
def test_invalid_origin_even_if_configured(origin):
    application = policy_app(security_settings(cors_origins=[origin]))
    result = call_http(application, method="POST", headers=[("host", "localhost"), ("origin", origin)])
    assert result[0] == 403 and result[2] == 0


def test_duplicate_origin_is_rejected():
    result = call_http(policy_app(security_settings()), method="POST", headers=[
        ("host", "localhost"), ("origin", LOCAL_ORIGIN), ("origin", LOCAL_ORIGIN),
    ])
    assert result[0] == 403 and result[2] == 0


@pytest.mark.parametrize("origin", ["http://LOCALHOST", "http://localhost:80", "http://localhost/"])
def test_origin_comparison_is_exact_not_canonicalized(origin):
    application = policy_app(security_settings(cors_origins=["http://localhost"]))
    result = call_http(application, method="POST", headers=[("host", "localhost"), ("origin", origin)])
    assert result[0] == 403


@pytest.mark.parametrize(("mode", "host", "origin", "expected"), [
    ("server", "API.EXAMPLE.TEST:443", REMOTE_ORIGIN, 204),
    ("desktop", "api.example.test", REMOTE_ORIGIN, 403),
    ("desktop", "127.0.0.1", REMOTE_ORIGIN, 403),
    ("server", "evil.example", REMOTE_ORIGIN, 403),
    ("server", "api.example.test", "https://evil.example", 403),
    ("server", "api.example.test", None, 204),
])
def test_server_desktop_policy_with_explicit_config(mode, host, origin, expected):
    application = policy_app(security_settings(
        mode=mode, trusted_hosts=["api.example.test"], cors_origins=[REMOTE_ORIGIN],
    ))
    headers = [("host", host)]
    if origin is not None:
        headers.append(("origin", origin))
    assert call_http(application, method="POST", headers=headers)[0] == expected


def test_host_allowlist_is_not_derived_from_origins():
    application = policy_app(security_settings(cors_origins=[REMOTE_ORIGIN]))
    result = call_http(application, headers=[("host", "app.example.test")])
    assert result[0] == 403


@pytest.mark.parametrize("host", ["localhost", "evil.example"])
def test_forwarded_headers_neither_grant_nor_remove_trust(host):
    result = call_http(policy_app(security_settings()), headers=[
        ("host", host), ("x-forwarded-host", "localhost" if host != "localhost" else "evil.example"),
        ("x-forwarded-proto", "https"), ("forwarded", "host=localhost;proto=https"),
        ("x-real-ip", "127.0.0.1"),
    ])
    assert result[0] == (204 if host == "localhost" else 403)


@pytest.mark.parametrize("host", ["127.0.0.1", "evil.example"])
def test_options_security_is_outside_cors(host):
    application = create_app(security_settings())
    assert application.user_middleware[0].cls is RequestSecurityMiddleware
    assert application.user_middleware[1].cls is CORSMiddleware
    status, body, received, headers = call_http(application, method="OPTIONS", headers=[
        ("host", host), ("origin", LOCAL_ORIGIN), ("access-control-request-method", "POST"),
    ])
    assert received == 0
    if host == "evil.example":
        assert status == 403 and json.loads(body) == {"detail": "Forbidden request host"}
        assert b"access-control-allow-origin" not in headers
    else:
        assert status == 200 and headers[b"access-control-allow-origin"] == LOCAL_ORIGIN.encode()


def test_security_config_is_snapshot_not_mutable_settings():
    async def downstream(scope, receive, send):
        await Response(status_code=204)(scope, receive, send)
    settings = security_settings()
    middleware = RequestSecurityMiddleware(downstream, settings=settings)
    settings.trusted_hosts.append("evil.example")
    settings.cors_origins.append("https://evil.example")
    assert call_http(middleware, headers=[("host", "evil.example")])[0] == 403
    assert call_http(middleware, method="POST", headers=[("host", "localhost"), ("origin", "https://evil.example")])[0] == 403


@pytest.mark.parametrize(("scope_type", "host", "passed"), [
    ("lifespan", None, True), ("websocket", "localhost", True),
    ("websocket", "evil.example", False), ("websocket", None, False),
])
def test_non_http_scopes(scope_type, host, passed):
    calls, sent = [], []
    scope = {"type": scope_type, "headers": [(b"host", host.encode())] if host else []}
    async def downstream(actual_scope, receive, send):
        assert actual_scope is scope
        calls.append(actual_scope)
    async def receive():
        pytest.fail("Security should not read this scope")
    async def send(message):
        sent.append(message)
    asyncio.run(RequestSecurityMiddleware(downstream, settings=security_settings())(scope, receive, send))
    assert bool(calls) is passed
    if not passed:
        assert sent == [{"type": "websocket.close", "code": 1008, "reason": "Forbidden request host"}]
