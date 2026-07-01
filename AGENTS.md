# AGENTS.md

## Product boundary

InvestScope is an analytical application for research and for assets the user actually owns and enters manually. It must never connect to a broker, create orders, execute trades, expose Buy/Sell actions, or implement paper trading.

Permanent Portfolio copy: “InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки”.

## Architecture

- `backend/app/modules/data_sources/contracts.py`: provider-neutral contracts and validation.
- `backend/app/modules/data_sources/providers.py`: demo and external read-only adapters.
- `backend/app/modules/data_sources/sync.py`: provider-independent synchronization orchestration.
- `backend/app/repositories/market_data.py`: idempotent SQLAlchemy persistence.
- `backend/app/api/market_data.py`: exact `/api/assets` and `/api/market` endpoints.
- `backend/app/modules/portfolio`: calculations over manually entered owned positions.
- `frontend/components/asset-market-data.tsx`: stored quote and history visualization.
- `frontend/components/portfolio-manager.tsx`: manual positions valued from saved quotes.

Analytics and API handlers must depend on `MarketDataProvider`, never directly on Alpha Vantage or the demo adapter. Provider adapters are read-only.

## Data rules

1. Normalize every datetime to UTC and reject naive Python datetimes.
2. Use `Decimal` for prices and financial calculations; use PostgreSQL `NUMERIC`.
3. Never replace missing market fields with zero.
4. Enforce OHLC relationships, nonnegative volume, and the database unique key `asset_id + timeframe + event_time + provider`.
5. Synchronization must be idempotent. An unchanged row is neither inserted nor updated.
6. Reject and log malformed provider rows. Do not accept future market data.
7. Keep `published_at`, `received_at`, and `inserted_at` semantically distinct.
8. Never log API keys or commit `.env` files.
9. Every latest/history/valuation query must filter by the configured provider. Cross-provider fallback is forbidden unless an API caller explicitly supplies the supported `provider` query parameter.
10. Demo cleanup must use `delete_demo_bars()`; do not expose a broad cleanup command that accepts an arbitrary provider.
11. Run the freshness guard before constructing a provider request group. A fresh saved quote must consume zero external requests.
12. Route every Alpha Vantage HTTP call through `AlphaVantageRequestGateway`; direct `httpx` calls outside that gateway are forbidden.
13. Count successful and failed external requests in UTC days, reserve configured capacity, and preflight the whole sync request group.
14. Never retry a 429 automatically. Respect the reported retry delay or configured cooldown.
15. Provider status responses and frontend contracts must never contain API keys or secret-derived values.
16. Do not add automatic bulk sync, background polling, broker connectivity, orders, or transaction actions.
17. Apply the configured monotonic interval before every individual Alpha Vantage HTTP call, not after a sync group.
18. Keep one process-wide async lock and a PostgreSQL transaction-level advisory lock around slot wait plus HTTP execution.
19. Use `provider_burst_limit`, `provider_daily_limit`, and fallback `provider_rate_limit` as distinct error categories.
20. Keep Alpha Vantage transport params separate from log metadata. `TIME_SERIES_DAILY` may send only function, symbol, compact outputsize, JSON datatype and the secret key.
21. Never pass timeframe, date ranges, provider names, request group ids or throttle settings to Alpha Vantage.
22. Map Alpha Vantage `Error Message` to `provider_invalid_request`/HTTP 502, not to an unknown asset response.
23. For daily bars, derive fetch freshness from `received_at`; never use midnight `event_time` as a direct age measurement.
24. Keep `is_fetch_stale` separate from `is_market_data_stale`, and do not expect a new weekday session before configured close or during weekends.

## Portfolio valuation

- Ownership comes only from user input, never from an external account.
- Use only persisted quotes for current valuation.
- Include source and actual `received_at` beside every price.
- Mark missing-price positions as unvalued.
- Exclude unvalued positions and their cost basis from portfolio return; report their count and total recorded cost separately.

## Change checklist

- Add an Alembic migration for schema changes.
- Add tests for validation, provider failure mapping, persistence idempotency and API behavior.
- Run:

```bash
cd backend && pytest
cd frontend && npm run build
cd backend && python -m alembic -c alembic.ini upgrade head --sql
```
