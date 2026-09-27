# InvestScope API

FastAPI service for investment research and analytics of positions entered manually by the user. See the repository-level README for setup.

## Development CORS and dependency compatibility

The default browser origin allowlist is `http://127.0.0.1:3200`,
`http://localhost:3200`, and `http://localhost:3000`. Port 3200 is used by
`npm run dev`; localhost:3000 remains allowed for the existing Docker frontend
loopback mapping `127.0.0.1:3000:3000`. Root `.env.example` and Compose use the same list.
Override the entire list with the JSON-valued `INVESTSCOPE_CORS_ORIGINS` environment
variable, including in Compose. No wildcard or external origin is enabled by
default; SEC uploads still require an explicitly allowed loopback Origin.
Existing local `.env` overrides take precedence and are not modified automatically.

The SEC upload adapter uses private Starlette lifecycle hooks verified with
FastAPI 0.138.2 and Starlette 1.3.1. The direct requirement
`starlette>=1.3.1,<1.4` retains that minor family; installed FastAPI requires
`starlette>=0.46.0`, so the constraints are compatible. Review and rerun upload
cleanup/security tests before widening this range; no dependency upgrade is
needed for this constraint.

## Global API request security (Stage 4A.1)

`RequestSecurityMiddleware` is pure ASGI, registered last in `create_app` after
CORS, so Host/Origin rejection occurs before CORS preflight, routing, body reads,
multipart spooling, dependencies, DB access or provider calls. It uses an immutable
snapshot of its constructor Settings, not FastAPI dependency overrides.

- Every HTTP request (including GET, HEAD, OPTIONS, health and docs) requires one
  valid Host. A single shared authority parser handles hostname/IPv4 and bracketed
  IPv6 plus an optional valid port, rejecting whitespace, userinfo and URL paths.
- Desktop permits only `localhost`, `127.0.0.1`, `::1` even when extra hosts are
  configured. Server permits loopback plus explicitly configured trusted hosts.
- Every method except GET/HEAD/OPTIONS checks Origin when present. Missing Origin
  with valid Host remains allowed for non-browser clients. Duplicate/malformed
  Origin and `null` are rejected. HTTP(S) Origin must match `cors_origins` exactly:
  no case, default-port or trailing-slash normalization. Desktop additionally
  requires a loopback origin; server permits explicitly allowed remote origins.
- `INVESTSCOPE_TRUSTED_HOSTS` is a JSON list of allowed **HTTP Host names**, not
  browser origins. Default: `["localhost","127.0.0.1","::1"]`. Entries contain no
  scheme, port, path, query, fragment, userinfo or surrounding whitespace; IPv6
  entries have no brackets. DNS comparison is case-insensitive. Invalid entries,
  including `*`, fail Settings validation at startup rather than being ignored.
- `INVESTSCOPE_CORS_ORIGINS` is the separate browser-origin allowlist. It never
  grants Host trust. `testserver` is not in the production allowlist.
- Forwarded, X-Forwarded-* and X-Real-IP do not affect security decisions.
  Lifespan passes through unchanged. WebSocket handshakes check Host and close
  invalid requests with code 1008; no WebSocket Origin policy is added.
- Rejected HTTP requests return 403 with exactly `{"detail":"Forbidden request host"}`
  or `{"detail":"Forbidden request origin"}`. No offending header/allowlist is echoed.
- SEC import-json keeps its stricter loopback-only endpoint guard in both modes,
  even if the global server configuration allows a remote Host/Origin.

For intentional remote **server** deployments, example configuration is:

```dotenv
INVESTSCOPE_MODE=server
INVESTSCOPE_TRUSTED_HOSTS=["localhost","127.0.0.1","::1","api.example.com"]
INVESTSCOPE_CORS_ORIGINS=["https://app.example.com"]
```

Docker publishes frontend `127.0.0.1:3000:3000`, backend `127.0.0.1:8000:8000`,
and PostgreSQL `127.0.0.1:5432:5432`. Other machines cannot access them by default.
Remote operators must separately change the intended published interface, set
TRUSTED_HOSTS, and set browser CORS_ORIGINS; server mode alone does not expose ports.
Container-internal `db:5432` and the localhost backend healthcheck are unchanged.

Security regressions use explicit per-app configuration, isolated SQLite and mock
providers. Direct ASGI receive counters prove denied requests read zero body bytes,
including legacy CSV with File dependencies. Portfolio/position JSON without
Content-Type keeps the existing 422; positive controls use application/json and
return 201. No parser or business formula is changed.

Known boundaries:

- The pre-existing Compose frontend value
  `NEXT_PUBLIC_API_URL=http://backend:8000/api/v1` cannot resolve in a browser if
  included in its bundle. This stage does not fix frontend API configuration.
  A future server-side request with `Host: backend:8000` also requires explicitly
  adding `backend` to INVESTSCOPE_TRUSTED_HOSTS.
- Because security is outside CORS, its 403 responses may have no CORS headers;
  browser JavaScript may see a generic CORS/network error instead of readable 403.
- This boundary is not authentication and does not protect against a malicious
  local/non-browser client using an allowed Host and omitting Origin. Reverse-proxy
  trust and Sec-Fetch-Site policy remain out of scope.

## Offline SEC JSON import (Stage 4A)

Use official SEC submissions/companyfacts JSON obtained out of band. This is not
an SEC downloader or an attempt to bypass access controls. The API and existing
`python -m app.commands.fundamentals import-sec-json --symbol AAPL --submissions-file <file.json> --companyfacts-file <file.json>`
CLI share `SecManualJsonImportService`, the SEC parsers and one atomic transaction.
CLI arguments/stdout remain unchanged.

`POST /api/fundamentals/{symbol}/import-json` accepts `multipart/form-data` with
exactly two file parts, `submissions` and `companyfacts`. The path is the only
symbol input. No server paths, URLs, archives, directories or batch import.
Success is HTTP 200 with the existing `FundamentalSyncView` counters:
`symbol`, `cik`, `provider`, `profile_created`, `profile_updated`,
`filings_inserted`, `filings_updated`, `facts_inserted`, `facts_skipped`,
`facts_rejected`, `skipped`, `skip_reason`, `warning`, `received_at`.

Security runs **before** multipart parsing, in both server and desktop modes:

- Exactly one valid loopback Host: `localhost`, `127.0.0.1` or bracketed `::1`,
  with an optional valid port. `testserver` is not allowed.
- Missing Origin is allowed for local non-browser clients. A supplied Origin
  must be one valid HTTP(S) loopback origin exactly in `settings.cors_origins`.
  Null, duplicate and external origins are rejected, even if CORS lists them.
- Parse the Content-Type media type; use `request.form(max_files=2, max_fields=0)`.
  The endpoint-local lifecycle adapter delegates all multipart grammar to
  Starlette/python-multipart, checks completed parsing and closes partially
  spooled files on errors. This adapter does not patch the global multipart parser.
- The existing `sec_import_max_file_mb` (default 100 MiB) limits **each** file.
  Optional Content-Length is checked against `2 * per_file_limit + 1 MiB` before
  spooling; actual UploadFile size and bounded 64 KiB reads enforce file limits.
  Form/files close on success and failures. Filenames are labels only: strip both
  kinds of path separators, controls and drive colons; cap at 500 characters;
  use `submissions.json`/`companyfacts.json` for empty labels.

Common CLI/API validation intentionally became stricter: the normalized requested
symbol must belong to submissions.tickers; both CIKs must normalize identically;
another Asset must not already own that CIK (including a requested Asset with
null CIK). Existing different-CIK Assets are never reassigned. At most one Asset
is created, retaining Equity/USD/active defaults and the submissions name.
Descriptive strings are capped at actual model limits (Asset name 160, exchange
32; SEC metadata uses its own limits). Oversized raw identity fields are rejected,
not truncated into potentially colliding identities.

Decode UTF-8/BOM JSON with `parse_float=Decimal`, ordinary integer decoding and
NaN/Infinity rejection. All decode/parse/DB work runs sequentially in one worker
invocation; the importer commits once or rolls back all changes. Re-import
updates existing metadata/timestamps and reports skipped facts without duplicate
Assets/filings/facts. Provenance remains `sec_edgar` / `manual_json`, sanitized
source filenames and one UTC imported_at. Existing GET endpoints remain usable.
No schema migration, external requests or extra dependencies are required.

Errors use existing FastAPI detail conventions: 400 syntax/multipart/length,
403 Host/Origin, 409 SEC identity conflict, 413 size, 415 media type, 422 SEC
structure/CIK/symbol validation, 500 safe transaction/internal failure. Domain
errors include code/provider/message, never SQL, raw JSON, paths or traceback.

### Verification and residual limits

Normal pytest never starts Docker. PostgreSQL runtime checks are separate,
explicit checks against a disposable test DB only; never use the working DB.

- Live `sec_gateway.py` still uses standard float JSON decoding (separate work).
- A malicious local process with absent/dishonest Content-Length can still force
  Starlette to spool before the endpoint-level actual file-size check.
- SQLite's existing 10-second busy timeout is unchanged; a long writer can
  block other writes and receive a safe transaction failure. No retry/queue/lock.
- Multiple Asset/share classes for one SEC CIK are not supported by this import.
- Global Host/Origin protection now covers portfolio CSV, provider sync and other
  mutations; authentication and the remaining local-client threats are separate.
- Root README/.env port 8000 versus local frontend 18000 remains separate cleanup.
- Two default 100 MiB files may decode into several GiB of Python objects;
  revisit the desktop limit using measured real SEC payloads in a later stage.
- Concurrent duplicate imports are not serialized; Stage 4B must disable the
  Import button during a request. Backend race hardening remains separate.
- The local multipart cleanup adapter uses Starlette lifecycle hooks; keep its
  malformed/truncated-upload resource-closure tests when upgrading Starlette.
