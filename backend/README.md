# InvestScope API

FastAPI service for investment research and analytics of positions entered manually by the user. See the repository-level README for setup.

## Development CORS and dependency compatibility

The default browser origin allowlist is `http://127.0.0.1:3200`,
`http://localhost:3200`, and `http://localhost:3000`. Port 3200 is used by
`npm run dev`; localhost:3000 remains allowed for the existing Docker frontend
mapping `3000:3000`. Root `.env.example` and Compose use the same list.
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
  spooled files on errors. No global middleware/parser patch is installed.
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
- CSRF review of portfolio CSV, market sync and other mutations remains separate.
- Root README/.env port 8000 versus local frontend 18000 remains separate cleanup.
- Two default 100 MiB files may decode into several GiB of Python objects;
  revisit the desktop limit using measured real SEC payloads in a later stage.
- Concurrent duplicate imports are not serialized; Stage 4B must disable the
  Import button during a request. Backend race hardening remains separate.
- The local multipart cleanup adapter uses Starlette lifecycle hooks; keep its
  malformed/truncated-upload resource-closure tests when upgrading Starlette.
