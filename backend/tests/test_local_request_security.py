import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.local_request_security import require_local_request


def request_with(headers: list[tuple[str, str]]) -> Request:
    return Request({"type": "http", "headers": [
        (key.encode("ascii"), value.encode("ascii")) for key, value in headers
    ]})


@pytest.mark.parametrize("host", [
    "localhost", "localhost:18000", "127.0.0.1", "127.0.0.1:7",
    "[::1]", "[::1]:65535", "LOCALHOST:3000",
])
def test_local_host_parsing(host: str) -> None:
    require_local_request(request_with([("host", host)]), allowed_origins=[])


@pytest.mark.parametrize("host", [
    "testserver", "evil.example", "evillocalhost", "localhost.evil", "localhost.",
    "localhost:", "localhost:65536", "localhost:-1", "localhost:abc", "localhost:1:2",
    "user@localhost", "localhost/path", "localhost?x", "localhost#x", "localhost\\x",
    "::1", "[::1", "[::1]evil", "[::2]", "127.1", "2130706433", " localhost", "",
])
def test_rejects_non_loopback_or_malformed_host(host: str) -> None:
    with pytest.raises(HTTPException) as error:
        require_local_request(request_with([("host", host)]), allowed_origins=[])
    assert error.value.status_code == 403


@pytest.mark.parametrize("headers", [[], [("host", "localhost"), ("host", "127.0.0.1")]])
def test_missing_or_duplicate_host(headers) -> None:
    with pytest.raises(HTTPException) as error:
        require_local_request(request_with(headers), allowed_origins=[])
    assert error.value.status_code == 403


@pytest.mark.parametrize("origin", [
    "null", "https://evil.example", "http://localhost/", "http://localhost/path",
    "http://user@localhost", "http://localhost?x", "file://localhost", "localhost",
    "http://[::1]evil", "http://localhost:65536", "http://localhost:1 http://localhost:2",
])
def test_invalid_origin_rejected_even_if_cors_lists_it(origin: str) -> None:
    with pytest.raises(HTTPException) as error:
        require_local_request(
            request_with([("host", "127.0.0.1"), ("origin", origin)]), allowed_origins=[origin],
        )
    assert error.value.status_code == 403


@pytest.mark.parametrize("origin", ["http://localhost:3000", "https://127.0.0.1", "http://[::1]:1234"])
def test_origin_requires_exact_allowlist_match(origin: str) -> None:
    request = request_with([("host", "localhost"), ("origin", origin)])
    require_local_request(request, allowed_origins=[origin])
    with pytest.raises(HTTPException):
        require_local_request(request, allowed_origins=[origin + "/"])


def test_duplicate_origin() -> None:
    with pytest.raises(HTTPException) as error:
        require_local_request(request_with([
            ("host", "localhost"), ("origin", "http://localhost"), ("origin", "http://localhost"),
        ]), allowed_origins=["http://localhost"])
    assert error.value.status_code == 403
