# InvestScope

## Overview

InvestScope is a read-only analytics platform for researching public companies. It combines persisted market data, official SEC filings and XBRL facts, deterministic fundamental-metric selection, and analytics for positions entered manually by the user.

The application has no brokerage integration, does not execute real or simulated orders, and does not provide personalized investment advice.

## Key features

- ingestion of official SEC submissions and companyfacts JSON;
- XBRL concept normalization with original taxonomy, concept, unit, and filing provenance preserved;
- quarterly, annual, and trailing-twelve-month (TTM) metrics;
- point-in-time analysis through timezone-aware `as_of` values;
- deterministic canonical fact selection;
- explicit handling of comparative facts, restatements, and amendments;
- derived metrics with formulas and `calculation_components`;
- full `source_facts` audit trail;
- UTC/Decimal-safe PostgreSQL storage for daily market data;
- portfolio analytics for manually entered owned positions, without trading;
- deterministic historical testing of analytical SMA signals;
- responsive Next.js frontend with independent loading, error, and empty states.

## Screenshots

Planned screenshot locations:

- [Asset analysis](docs/screenshots/asset-analysis.png)
- [Portfolio analytics](docs/screenshots/portfolio.png)
- [Historical signal testing](docs/screenshots/backtesting.png)

The repository intentionally contains placeholders only. Add reviewed screenshots to `docs/screenshots/` before publication.

## Architecture

```mermaid
flowchart LR
    SEC["Official SEC JSON<br/>or SEC EDGAR read-only API"]
    Market["Read-only market providers"]
    Validate["Validation and normalization"]
    DB[("PostgreSQL")]
    API["FastAPI"]
    UI["Next.js frontend"]

    SEC --> Validate
    Market --> Validate
    Validate --> DB

    DB --> Fundamentals["Fundamental metrics engine"]
    DB --> MarketLayer["Market-data layer"]
    DB --> Portfolio["Portfolio analytics"]
    Demo["Fixed deterministic demo series"] --> Backtesting["Backtesting module"]

    Fundamentals --> API
    MarketLayer --> API
    Portfolio --> API
    Backtesting --> API
    API --> UI
```

See [docs/architecture.md](docs/architecture.md) for data flows, point-in-time semantics, provenance, and API boundaries.

## Technology stack

- Python 3.12+;
- FastAPI 0.115–0.x and Pydantic Settings 2.x;
- SQLAlchemy 2.x, Alembic 1.14–1.x, psycopg 3.2–3.x;
- PostgreSQL 17;
- Next.js 15, React 19, TypeScript 5.7+ in strict mode;
- pytest 8.3–8.x;
- Docker Compose.

Version ranges come from `backend/pyproject.toml`, `frontend/package.json`, the lockfile, and Docker configuration.

## Project structure

```text
backend/                 FastAPI application, services, repositories, schemas and tests
backend/alembic/         PostgreSQL schema migrations
frontend/                Next.js App Router frontend
data/                    Local import workspace; SEC JSON is intentionally ignored
docs/                    Architecture and portfolio documentation
docs/screenshots/        Reviewed screenshots added before publication
output/                  Local reports and test output
docker-compose.yml       PostgreSQL, backend and frontend development stack
```

## Data provenance

Fundamental metric responses keep selection and calculation evidence separate:

- `selected_fact` is the canonical SEC fact selected for a directly reported metric;
- `alternative_facts` are other eligible facts returned only when requested;
- `source_facts` is the complete audit set considered for the result;
- `calculation_components` contains only the operands that actually entered a derived calculation.

Comparative facts remain in `source_facts` so a result can be audited, but repeated comparative values are not counted again as a new quarter or TTM component. Amendments and restatements are selected only when they are available at the requested `as_of` time.

## Local setup

The commands below use Windows PowerShell. No real credentials belong in the repository.

### 1. Create local environment files

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
```

Replace the placeholder PostgreSQL password in `.env`. Keep external API keys only in the ignored `.env` file.

### 2. Start PostgreSQL

```powershell
docker compose up -d db
```

### 3. Install the backend and apply migrations

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item ..\.env .env

# A host-run backend connects through localhost rather than the Compose service name `db`.
$env:INVESTSCOPE_DATABASE_URL = "postgresql+psycopg://investscope:replace-with-local-password@localhost:5432/investscope"
python -m alembic -c alembic.ini upgrade head
```

### 4. Start the backend

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Install and start the frontend

In a second PowerShell terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Open <http://127.0.0.1:3200>. API documentation is available at <http://127.0.0.1:8000/docs> and health status at <http://127.0.0.1:8000/health>.

For the complete container stack, run `docker compose up --build` from the repository root and open <http://localhost:3000>.

## SEC offline import

Live SEC access may reject automated clients even with an identifying User-Agent. InvestScope therefore supports a local, non-network importer for files obtained from the official SEC endpoints.

From the activated backend environment:

```powershell
python -m app.commands.fundamentals set-company `
  --symbol AAPL `
  --cik 0000320193 `
  --name "Apple Inc." `
  --exchange Nasdaq

python -m app.commands.fundamentals import-sec-json `
  --symbol AAPL `
  --submissions-file ".\local-data\AAPL-submissions.json" `
  --companyfacts-file ".\local-data\AAPL-companyfacts.json"
```

The importer validates local `.json` files, file size, SEC structure, and matching CIK values. It reuses the production parsers and XBRL mapping, is transactional and idempotent, preserves amended filings, and performs no network request. There is no public file-upload endpoint.

## Testing

Backend:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q --basetemp="..\output\pytest-public-check"
```

Frontend:

```powershell
Set-Location frontend
npm run typecheck
npm run build
node --experimental-strip-types --test tests/api-base.test.mjs
```

Current verified status:

- backend: **133 passed**;
- TypeScript strict typecheck: **passed**;
- Next.js production build: **passed**;
- legacy API URL tests: **3 passed**.

The project does not currently include a frontend component-test framework.

## Known limitations

- part of the frontend asset catalogue still depends on `demo-data`;
- historical testing uses a fixed deterministic demonstration series;
- commissions, spreads, taxes, liquidity constraints, and corporate actions are not modelled;
- the filings endpoint has limit/offset controls but no full pagination metadata;
- a raw-facts explorer is not implemented;
- no live production deployment is currently provided;
- live SEC access can be restricted, so offline official JSON import remains supported;
- there is no authentication or multi-user authorization layer yet.

## Disclaimer

InvestScope is for research and educational analytics only. It is not investment advice. It does not connect to a broker and does not execute real or simulated trades or orders.
