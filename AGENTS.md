# AGENTS.md

## Project intent

InvestScope is an investment research application and an analytical register of assets the user actually owns and enters manually.

The permanent product boundary is: “InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки”.

## Repository map

- `backend/app/api`: thin FastAPI transport layer and owned-position CRUD.
- `backend/app/modules/portfolio`: calculations over user-entered positions.
- `backend/app/models`: SQLAlchemy persistence models.
- `backend/app/schemas`: external Pydantic contracts.
- `backend/tests`: pytest tests.
- `frontend/app/portfolio`: portfolio analytics page.
- `frontend/components/portfolio-manager.tsx`: manual position entry and CSV import UI.
- `frontend/lib`: shared types, fixtures and API helpers.

## Engineering rules

1. Use timezone-aware `datetime` values and normalize them to UTC. Use SQL `DATE` for date-only fields such as `purchase_date`.
2. Use `Decimal` for prices, money, quantities and financial calculations in Python. Persist them as PostgreSQL `NUMERIC`.
3. Type all public Python functions and TypeScript code. Keep strict TypeScript enabled.
4. Keep API handlers small and put portfolio calculations in `modules/portfolio`.
5. Add an Alembic migration for every deployed schema change. The initial migration may only be amended before first deployment.
6. Add or update pytest coverage for behavior changes and run `pytest` before handoff.
7. Label market fixtures, scenario outputs and model assumptions clearly.
8. Never log secrets or commit `.env` files.

## Portfolio boundary

- A position represents an asset the user reports as owned; it is not an order or an execution record.
- Allowed actions are create, update, delete and CSV import of positions.
- Do not add order sides, order tickets, fills, execution statuses, broker SDKs, exchange connectivity, custody, or payment flows.
- Do not infer ownership from external accounts. The user is the source of ownership data.
- Keep the no-broker/no-trades explanation visible on the Portfolio page and present in the Portfolio API response.

## Validation commands

```bash
cd backend && pytest
cd frontend && npm run typecheck && npm run build
docker compose config
```
