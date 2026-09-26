import asyncio
import io
import json
import threading
from collections.abc import Iterator
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.requests import Request

from app.api import fundamentals as api
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import app
from app.models import Asset, CompanyFiling, CompanyProfile, FinancialFact
from app.modules.fundamental_analysis.manual_import import SecImportFileTooLargeError
from app.repositories import FundamentalRepository
from test_sec_manual_import import companyfacts_payload, numeric_companyfacts_bytes, submissions_payload

URL = "/api/fundamentals/AAPL/import-json"
ORIGIN = "http://localhost:3000"


@pytest.fixture
def import_settings() -> Settings:
    return Settings(_env_file=None, mode="server", sec_import_max_file_mb=1,
                    cors_origins=[ORIGIN, "http://127.0.0.1:3200", "http://[::1]:3000", "https://evil.example"])


@pytest.fixture
def import_client(db_session: Session, import_settings: Settings) -> Iterator[TestClient]:
    def database():
        # Production semantics: one clean session per import, no shared pending state.
        with Session(db_session.get_bind(), expire_on_commit=False, autoflush=False) as session:
            yield session

    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_settings] = lambda: import_settings
    try:
        with TestClient(app, base_url="http://127.0.0.1") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


def uploads(submissions=None, companyfacts=None, names=("submissions.json", "companyfacts.json")):
    def raw(value, default):
        return value if isinstance(value, bytes) else json.dumps(default() if value is None else value).encode()
    return [
        ("submissions", (names[0], raw(submissions, submissions_payload), "application/json")),
        ("companyfacts", (names[1], raw(companyfacts, companyfacts_payload), "application/json")),
    ]


def counts(session):
    return tuple(session.scalar(select(func.count()).select_from(model))
                 for model in (Asset, CompanyProfile, CompanyFiling, FinancialFact))


@pytest.mark.parametrize("mode", ["server", "desktop"])
@pytest.mark.parametrize(("host", "origin", "expected_status"), [
    ("127.0.0.1", "http://127.0.0.1:3200", 200),
    ("localhost", "http://localhost:3200", 200),
    ("127.0.0.1", "https://evil.example", 403),
    ("testserver", "http://127.0.0.1:3200", 403),
])
def test_fresh_clone_cors_defaults_for_sec_import(
    import_client, import_settings, monkeypatch, mode, host, origin, expected_status,
):
    monkeypatch.delenv("INVESTSCOPE_CORS_ORIGINS", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.cors_origins == [
        "http://127.0.0.1:3200", "http://localhost:3200", "http://localhost:3000",
    ]
    import_settings.cors_origins = defaults.cors_origins
    import_settings.mode = mode
    response = import_client.post(URL, files=uploads(), headers={"host": host, "origin": origin})
    assert response.status_code == expected_status, response.text


def test_cors_environment_override_remains_source_of_truth(import_client, import_settings, monkeypatch):
    origin = "http://127.0.0.1:4311"
    monkeypatch.setenv("INVESTSCOPE_CORS_ORIGINS", json.dumps([origin]))
    overridden = Settings(_env_file=None)
    assert overridden.cors_origins == [origin]
    import_settings.cors_origins = overridden.cors_origins
    assert import_client.post(URL, files=uploads(), headers={"origin": origin}).status_code == 200
    for default_origin in ("http://127.0.0.1:3200", "http://localhost:3200"):
        assert import_client.post(URL, files=uploads(), headers={"origin": default_origin}).status_code == 403


@pytest.mark.parametrize("mode", ["server", "desktop"])
@pytest.mark.parametrize(("host", "origin"), [
    ("127.0.0.1", ORIGIN), ("localhost:18000", ORIGIN), ("[::1]:18000", "http://[::1]:3000"),
    ("127.0.0.1:8000", None),
])
def test_loopback_import_success(import_client, import_settings, db_session, mode, host, origin):
    import_settings.mode = mode
    headers = {"host": host}
    if origin is not None:
        headers["origin"] = origin
    response = import_client.post(URL, files=uploads(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "symbol", "cik", "provider", "profile_created", "profile_updated", "filings_inserted",
        "filings_updated", "facts_inserted", "facts_skipped", "facts_rejected", "skipped",
        "skip_reason", "warning", "received_at",
    }
    assert body["facts_inserted"] == 2 and body["facts_rejected"] == 1
    assert body["provider"] == "sec_edgar" and body["cik"] == "0000320193"
    assert counts(db_session) == (1, 1, 2, 2)
    asset = db_session.scalar(select(Asset))
    assert (asset.name, asset.asset_type, asset.currency, asset.provider_symbol, asset.is_active) == (
        "Apple Inc.", "Equity", "USD", "AAPL", True,
    )


@pytest.mark.parametrize("mode", ["server", "desktop"])
@pytest.mark.parametrize("headers", [
    [("host", "127.0.0.1"), ("origin", "https://evil.example")],
    [("host", "127.0.0.1"), ("origin", "null")],
    [("host", "evil.example"), ("origin", ORIGIN)], [("host", "evil.example")],
    [("host", "testserver")], [("host", "localhost:invalid")],
    [("host", "localhost"), ("host", "127.0.0.1")],
    [("host", "localhost"), ("origin", ORIGIN), ("origin", ORIGIN)], [],
])
def test_security_rejection_precedes_form_and_import(
    import_client, import_settings, monkeypatch, db_session, mode, headers,
):
    import_settings.mode = mode
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected security request reached multipart/import")
    monkeypatch.setattr(Request, "form", forbidden)
    monkeypatch.setattr(api.SecManualJsonImportService, "import_bytes", forbidden)
    request = import_client.build_request("POST", URL, files=uploads())
    request.headers.pop("host")
    # Preserve duplicate headers instead of collapsing them into a dict.
    request.headers = httpx.Headers(list(request.headers.multi_items()) + headers)
    if not headers:
        # TestClient injects Host from URL even after it is removed from HTTPX.
        # Model the actual wire-level absence at the ASGI boundary instead.
        async def without_host(scope, receive, send):
            if scope["type"] == "http":
                scope = {**scope, "headers": [(key, value) for key, value in scope["headers"] if key != b"host"]}
            await app(scope, receive, send)
        with TestClient(without_host, base_url="http://127.0.0.1") as no_host_client:
            response = no_host_client.send(request)
    else:
        response = import_client.send(request)
    assert response.status_code == 403
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize(("header", "value", "status"), [
    ("content-type", "application/json", 415), ("content-type", None, 415),
    ("content-type", "multipart/form-data-garbage; boundary=x", 415),
    ("content-length", "3145729", 413), ("content-length", "9" * 5000, 413),
    ("content-length", "-1", 400), ("content-length", "1.2", 400),
    ("content-length", "1, 2", 400), ("content-length", "+1", 400),
    ("content-length", "", 400),
])
def test_header_rejections_precede_form(import_client, monkeypatch, header, value, status):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid headers reached multipart parsing")
    monkeypatch.setattr(Request, "form", forbidden)
    request = import_client.build_request("POST", URL, files=uploads())
    request.headers.pop(header, None)
    if value is not None:
        request.headers[header] = value
    assert import_client.send(request).status_code == status


def test_duplicate_content_length_precedes_form(import_client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Duplicate Content-Length reached parsing")
    monkeypatch.setattr(Request, "form", forbidden)
    request = import_client.build_request("POST", URL, files=uploads())
    request.headers = httpx.Headers(list(request.headers.multi_items()) + [("content-length", "10")])
    assert import_client.send(request).status_code == 400


@pytest.mark.parametrize("parts", [
    ["submissions"], ["companyfacts"], ["submissions", "submissions"],
    ["companyfacts", "companyfacts"], ["submissions", "other"],
    ["submissions", "companyfacts", "other"],
])
def test_multipart_shape(import_client, db_session, parts):
    response = import_client.post(URL, files=[(name, ("input.json", b"{}")) for name in parts])
    assert response.status_code == 400
    assert counts(db_session) == (0, 0, 0, 0)


def test_text_field_is_not_a_file_and_extra_fields_are_rejected(import_client):
    for parts in [
        [("submissions", (None, "{}")), uploads()[1]],
        uploads() + [("symbol", (None, "AAPL"))],
        uploads() + [("path", (None, "/private/local.json"))],
    ]:
        assert import_client.post(URL, files=parts).status_code == 400


@pytest.mark.parametrize(("body", "content_type"), [
    (b"nonsense", "multipart/form-data; boundary=example"),
    (b"nonsense", "multipart/form-data"),
    (b"--example\r\nMissing-Colon\r\n\r\nxxx", "multipart/form-data; boundary=example"),
])
def test_malformed_multipart(import_client, body, content_type):
    response = import_client.post(URL, content=body, headers={"content-type": content_type})
    assert response.status_code == 400


@pytest.mark.parametrize("ending", ["broken_header", "unfinished_file", "missing_end"])
def test_malformed_multipart_closes_already_spooled_files(import_client, monkeypatch, ending):
    opened = []
    original_init = UploadFile.__init__
    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        opened.append(self)
    monkeypatch.setattr(UploadFile, "__init__", tracked_init)
    request = import_client.build_request("POST", URL, files=uploads())
    body = request.read()
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    if ending == "broken_header":
        body = body.rsplit(b"--" + boundary, 1)[0] + b"--" + boundary + b"\r\nBroken-Header\r\n\r\n"
    elif ending == "unfinished_file":
        body = body.rsplit(b"--" + boundary, 1)[0]
    else:
        body = body[:-4]  # No terminal boundary marker/CRLF.
    response = import_client.post(URL, content=body, headers={"content-type": request.headers["content-type"]})
    assert response.status_code == 400
    assert opened and all(upload.file.closed for upload in opened)


@pytest.mark.parametrize("part", ["submissions", "companyfacts"])
@pytest.mark.parametrize("raw", [b"{invalid", b"\xff", b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'])
def test_invalid_json_is_400(import_client, db_session, part, raw):
    response = import_client.post(URL, files=uploads(**{part: raw}))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "sec_import_invalid_json"
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("part", ["submissions", "companyfacts"])
@pytest.mark.parametrize("payload", [{}, [], "not an object"])
def test_valid_json_invalid_sec_structure_is_422(import_client, db_session, part, payload):
    response = import_client.post(URL, files=uploads(**{part: payload}))
    assert response.status_code == 422
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("part", ["submissions", "companyfacts"])
@pytest.mark.parametrize("include_length", [True, False])
def test_actual_file_size_limit(import_client, db_session, monkeypatch, part, include_length):
    def forbidden(*args, **kwargs):
        pytest.fail("Oversized upload reached JSON decoding")
    monkeypatch.setattr(api.SecManualJsonImportService, "import_bytes", forbidden)
    request = import_client.build_request("POST", URL, files=uploads(**{part: b" " * (1024 * 1024 + 1)}))
    if not include_length:
        request.headers.pop("content-length")
    assert import_client.send(request).status_code == 413
    assert counts(db_session) == (0, 0, 0, 0)


def test_absent_content_length_and_utf8_bom_allowed(import_client):
    request = import_client.build_request("POST", URL, files=uploads(
        submissions=b"\xef\xbb\xbf" + json.dumps(submissions_payload()).encode(),
    ))
    request.headers.pop("content-length")
    assert import_client.send(request).status_code == 200


def test_bounded_reads_enforce_actual_bytes_even_with_missing_or_false_size():
    class BoundedUpload(UploadFile):
        async def read(self, size=-1):
            assert 0 < size <= 64 * 1024
            return await super().read(size)
    for size in (None, 1):
        upload = BoundedUpload(io.BytesIO(b"12345"), size=size)
        with pytest.raises(SecImportFileTooLargeError):
            asyncio.run(api._read_import_upload(upload, 4))
        upload.file.close()
    upload = BoundedUpload(io.BytesIO(b"1234"), size=4)
    assert asyncio.run(api._read_import_upload(upload, 4)) == b"1234"
    upload.file.close()


@pytest.mark.parametrize("tickers", [None, "AAPL", [], [None, "bad symbol"], ["MSFT"]])
def test_ticker_membership_required(import_client, db_session, tickers):
    payload = submissions_payload()
    if tickers is None:
        payload.pop("tickers")
    else:
        payload["tickers"] = tickers
    response = import_client.post(URL, files=uploads(submissions=payload))
    assert response.status_code == 422
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("symbol", ["aapl", "NEW"])
def test_requested_symbol_only_with_canonical_ticker_membership(import_client, db_session, symbol):
    payload = submissions_payload()
    payload["tickers"] = ["OTHER", " " + symbol.lower() + " ", "THIRD"]
    response = import_client.post(f"/api/fundamentals/{symbol}/import-json", files=uploads(submissions=payload))
    assert response.status_code == 200
    assert counts(db_session)[0] == 1
    assert db_session.scalar(select(Asset)).symbol == symbol.upper()


def test_invalid_requested_symbol(import_client, db_session):
    assert import_client.post(URL.replace("AAPL", "bad%20symbol"), files=uploads()).status_code == 422
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("cik", [320193, "320193", "0000320193"])
def test_textual_cik_variants(import_client, cik):
    payload = submissions_payload()
    payload["cik"] = cik
    response = import_client.post(URL, files=uploads(submissions=payload))
    assert response.status_code == 200 and response.json()["cik"] == "0000320193"


@pytest.mark.parametrize("cik", ["0000000001", None, "invalid", "12345678901"])
def test_invalid_or_mismatching_cik(import_client, db_session, cik):
    payload = companyfacts_payload()
    payload["cik"] = cik
    assert import_client.post(URL, files=uploads(companyfacts=payload)).status_code == 422
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("saved_cik", [None, "320193", "0000320193"])
def test_existing_asset_reused(import_client, db_session, saved_cik):
    asset = Asset(symbol="AAPL", name="Existing", asset_type="Equity", currency="USD", cik=saved_cik)
    db_session.add(asset)
    db_session.commit()
    original_id = asset.id
    assert import_client.post(URL, files=uploads()).status_code == 200
    db_session.expire_all()
    assert asset.id == original_id and asset.cik == "0000320193"
    assert counts(db_session)[0] == 1


@pytest.mark.parametrize(("requested_exists", "requested_cik", "other_cik"), [
    (True, "0000000001", None), (False, None, "320193"),
    (True, None, "0000320193"), (True, "0000320193", "320193"),
])
def test_identity_conflict_changes_nothing(import_client, db_session, requested_exists, requested_cik, other_cik):
    if requested_exists:
        db_session.add(Asset(symbol="META", name="Requested", asset_type="Equity", currency="USD", cik=requested_cik))
    if other_cik:
        db_session.add(Asset(symbol="FB", name="Other", asset_type="Equity", currency="USD", cik=other_cik))
    db_session.commit()
    before = counts(db_session)
    payload = submissions_payload()
    payload["tickers"] = ["META"]
    response = import_client.post(URL.replace("AAPL", "META"), files=uploads(submissions=payload))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "sec_import_identity_conflict"
    if other_cik:
        assert "asset FB" in response.json()["detail"]["message"]
    assert counts(db_session) == before
    db_session.expire_all()
    if requested_exists:
        assert db_session.scalar(select(Asset).where(Asset.symbol == "META")).cik == requested_cik


def test_repeated_upload_provenance_and_read_endpoints(import_client, db_session):
    files = uploads(names=("C:\\private\\submissions.json", "/private/companyfacts.json"))
    first = import_client.post(URL, files=files)
    before = counts(db_session)
    second = import_client.post(URL, files=files)
    assert first.status_code == second.status_code == 200
    assert counts(db_session) == before == (1, 1, 2, 2)
    assert second.json()["facts_skipped"] == 2 and second.json()["facts_inserted"] == 0
    assert second.json()["profile_updated"] == 1 and second.json()["filings_updated"] == 2
    timestamps = set()
    for model, filename in [(CompanyProfile, "submissions.json"), (CompanyFiling, "submissions.json"), (FinancialFact, "companyfacts.json")]:
        for row in db_session.scalars(select(model)):
            assert row.provider == "sec_edgar" and row.ingestion_method == "manual_json"
            assert row.source_filename == filename
            assert row.imported_at.utcoffset().total_seconds() == 0
            timestamps.add(row.imported_at)
    assert len(timestamps) == 1
    for endpoint in ("profile", "filings", "facts", "metrics"):
        response = import_client.get(URL.replace("import-json", endpoint))
        assert response.status_code == 200
        assert "/private" not in response.text and "C:" not in response.text
    assert "private" not in first.text + second.text


@pytest.mark.parametrize("failure", ["insert_facts", "commit"])
def test_db_phase_failure_rolls_back_flushed_rows(import_client, db_session, monkeypatch, failure):
    def fail_repository(self, **kwargs):
        self.session.flush()
        assert counts(self.session)[:3] == (1, 1, 2)
        raise RuntimeError("private path /secrets/query.sql and SQL details")
    def fail_commit(self):
        self.flush()
        assert counts(self) == (1, 1, 2, 2)
        raise RuntimeError("private SQL commit details")
    if failure == "insert_facts":
        monkeypatch.setattr(FundamentalRepository, failure, fail_repository)
    else:
        monkeypatch.setattr(Session, failure, fail_commit)
    response = import_client.post(URL, files=uploads())
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "sec_import_transaction_failed"
    assert not any(word in response.text for word in ["private", "Traceback", "query.sql", "INSERT INTO"])
    assert counts(db_session) == (0, 0, 0, 0)


@pytest.mark.parametrize("outcome", ["success", "shape", "json", "oversize", "import", "unexpected"])
def test_all_uploads_closed(import_client, monkeypatch, outcome):
    opened = []
    original_init = UploadFile.__init__
    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        opened.append(self)
    monkeypatch.setattr(UploadFile, "__init__", tracked_init)
    files = uploads()
    expected = 200
    if outcome == "shape":
        files[1] = ("other", files[1][1])
        expected = 400
    elif outcome == "json":
        files = uploads(companyfacts=b"{")
        expected = 400
    elif outcome == "oversize":
        files = uploads(companyfacts=b" " * (1024 * 1024 + 1))
        expected = 413
    elif outcome in {"import", "unexpected"}:
        def fail(*args, **kwargs):
            raise RuntimeError("secret local path")
        if outcome == "import":
            monkeypatch.setattr(FundamentalRepository, "insert_facts", fail)
        else:
            monkeypatch.setattr(api.SecManualJsonImportService, "import_bytes", fail)
        expected = 500
    response = import_client.post(URL, files=files)
    assert response.status_code == expected
    assert len(opened) == 2 and all(upload.file.closed for upload in opened)
    assert "secret local path" not in response.text


def test_upload_no_network_and_single_worker_session(import_client, db_session, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline upload attempted outbound HTTP")
    # TestClient.send uses its in-process ASGI transport; bypass request() here.
    request = import_client.build_request("POST", URL, files=uploads(companyfacts=numeric_companyfacts_bytes("123456789012345.1234567890")))
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    loop_threads, db_threads, worker_calls = [], [], []
    original_threadpool = api.run_in_threadpool
    async def worker(function, *args, **kwargs):
        loop_threads.append(threading.get_ident())
        worker_calls.append(function)
        return await original_threadpool(function, *args, **kwargs)
    monkeypatch.setattr(api, "run_in_threadpool", worker)
    def record_query(*args):
        db_threads.append(threading.get_ident())
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_query)
    try:
        response = import_client.send(request)
    finally:
        event.remove(engine, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert len(worker_calls) == 1 and len(set(db_threads)) == 1
    assert set(loop_threads).isdisjoint(db_threads)
    assert db_session.scalar(select(FinancialFact)).value == Decimal("123456789012345.1234567890")


def test_import_openapi_documents_only_two_files_and_existing_response(import_client):
    schema = import_client.get("/openapi.json").json()
    path = "/api/fundamentals/{symbol}/import-json"
    assert "/api/v1/fundamentals/{symbol}/import-json" not in schema["paths"]
    operation = schema["paths"][path]["post"]
    body = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert body["required"] == ["submissions", "companyfacts"]
    assert set(body["properties"]) == {"submissions", "companyfacts"}
    assert body["additionalProperties"] is False
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response["$ref"].endswith("/FundamentalSyncView")
