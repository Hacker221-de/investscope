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
