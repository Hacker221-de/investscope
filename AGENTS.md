# AGENTS.md

## Product boundary

InvestScope is an analytical application for research and for assets the user actually owns and enters manually. It must never connect to a broker, create orders, execute trades, expose Buy/Sell actions, or implement paper trading.

Permanent Portfolio copy: “InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки”.

## Architecture

- `backend/app/modules/data_sources/contracts.py`: provider-neutral contracts and validation.
- `backend/app/modules/data_sources/providers.py`: demo and external read-only adapters.
- `backend/app/modules/data_sources/sync.py`: provider-independent synchronization orchestration.
- `backend/app/repositories/market_data.py`: idempotent SQLAlchemy persistence.
- `backend/app/modules/fundamental_analysis`: provider contract, SEC gateway, XBRL parsing,
  and point-in-time synchronization.
- `backend/app/repositories/fundamentals.py`: idempotent profile, filing, and fact persistence.
- `backend/app/api/fundamentals.py`: `/api/fundamentals` read and manual sync endpoints.
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
25. Route every SEC request through `SecEdgarRequestGateway` with the configured identifying User-Agent; never expose that contact through the API.
26. Store SEC CIK values as 10 zero-padded digits and validate accession numbers before persistence.
27. Preserve original XBRL taxonomy, concept, and unit beside normalized metrics. Missing values remain missing; negative financial facts are valid.
28. Classify instant, quarterly, annual, and YTD facts from period dates. A 10-Q form alone does not imply a quarterly duration.
29. Point-in-time queries must enforce fact `filed_at` and filing `acceptance_datetime` when available. An amendment is unavailable before publication.
30. SEC synchronization is manual, transactional, and idempotent. A fresh persisted sync must consume zero external requests.
31. Resolve SEC companies in this order: valid `Asset.cik`, persistent `sec_ticker_cache`, then the external ticker index. Never fetch the index for an Asset with a valid CIK.
32. The persistent ticker cache survives process restarts. An expired entry may be used with `sec_ticker_cache_stale` only after a temporary rate-limit, timeout, or network failure.
33. Apply the same one-request-per-second SEC limiter to `www.sec.gov` and `data.sec.gov`; parallel PostgreSQL workers share the SEC advisory lock.
34. Classify threshold/excessive-request HTML as `sec_rate_limit`; reserve `sec_access_denied` for actual access denial such as `Undeclared Automated Tool`. Never retry either automatically.
35. Do not attempt to bypass SEC access controls by swapping Python HTTP libraries or disguising request identity. Use the local manual JSON importer when official files are available out of band.
36. Manual SEC import accepts only size-limited local `.json` files, never URLs; validates both root structures and CIK agreement before database mutation; and never logs full JSON or local paths.
37. Keep manual import CLI-only. Do not expose a public upload endpoint without a separate security review.
38. Keep `provider="sec_edgar"` for imported records. Use `ingestion_method="manual_json"`, basename-only `source_filename`, and UTC `imported_at` to describe ingestion provenance.
39. Manual import must reuse SEC parsers/XBRL mapping, remain transactional and idempotent, preserve amendments, and never call a network gateway.
40. Canonical fundamental periods are keyed by normalized metric, unit, actual period start/end, and period type. Never use fiscal year/period or SEC frame as the sole period identity.
41. Keep raw facts immutable. Canonical selection is computed point-in-time and must retain selected, alternative, and calculation-source provenance.
42. A repeated comparative fact with the same value is not a new period. A changed later value is a restatement; an amendment is selectable only after its publication time.
43. Apply centralized XBRL concept priority before presenting a canonical metric, and surface conflicts instead of silently hiding them.
44. TTM requires four non-overlapping sequential canonical quarters with one unit. Never include YTD, annual, or repeated comparative values as extra quarters; annual fallback must be explicit.
45. Derived ratios return null plus a warning for missing inputs, zero denominators, or economically invalid denominators. Never synthesize missing inputs as zero.
46. Treat `PaymentsToAcquirePropertyPlantAndEquipment` as an outflow only in the FCF calculation; do not globally invert financial fact signs.
47. Point-in-time valuation uses only persisted prices from the configured market provider whose event and receipt timestamps are not later than `as_of`. Do not calculate P/E from non-positive earnings.
48. Fundamental frontend states must distinguish loading, transport error, no periods, conflicting facts, repeated comparative values, restatements, incomplete TTM, missing metrics, and stale prices.
49. A derived fiscal Q4 may use `annual - Q1 - Q2 - Q3` only for one fiscal year, one unit, compatible concepts, valid non-overlapping periods, and point-in-time available sources. Never persist it as a raw `FinancialFact`.
50. Derive cash-flow Q2/Q3/Q4 from 6M/9M/FY YTD differences. Do not wait for an annual filing to derive Q2 or Q3, and never expose Q4 before the 10-K source is available.
51. Every derived quarter must expose `derived`, `derivation_method`, `calculation`, confidence, warnings, and every operand in `source_facts`; the frontend must label it as calculated.
52. Debt aggregation must use non-overlapping components. Never add `LongTermDebt` to `LongTermDebtCurrent` or `LongTermDebtNoncurrent`; add short borrowing/commercial paper only when it is not already represented by the chosen aggregate.

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
