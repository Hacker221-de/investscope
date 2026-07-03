# InvestScope portfolio descriptions

## English

### Short project description

InvestScope is a read-only research platform that combines persisted market data with official SEC filings and normalized XBRL facts. It provides point-in-time fundamental metrics, transparent calculation provenance, analytics for manually entered portfolio positions, and deterministic historical signal testing without brokerage connectivity.

### Resume description

Designed and implemented a full-stack investment-research platform using FastAPI, PostgreSQL, SQLAlchemy, Alembic, Next.js, React, and TypeScript. Built idempotent market/SEC ingestion, deterministic XBRL fact selection, quarterly/annual/TTM metric derivation, point-in-time analysis, complete source provenance, and responsive analytical interfaces; validated by 133 backend tests and strict frontend builds.

### GitHub description

Read-only public-company research platform with SEC/XBRL ingestion, persisted market data, point-in-time fundamental analytics, auditable derived metrics, manual portfolio analysis, and deterministic signal backtesting. No brokerage integration or order execution.

### Engineering highlights

- provider-neutral market-data and fundamental-data contracts;
- UTC and Decimal-safe PostgreSQL persistence;
- idempotent synchronization with duplicate protection;
- shared throttling and daily-budget enforcement for external providers;
- offline transactional SEC JSON import with CIK validation;
- deterministic canonical selection across amendments and comparative facts;
- derived fiscal-quarter, YTD, TTM, ratio, growth, debt, and valuation metrics;
- strict separation of calculation operands and complete source-fact audit evidence;
- point-in-time `as_of` filtering that prevents future-data leakage;
- partial-valuation handling for portfolio positions without quotes;
- typed FastAPI and TypeScript contracts;
- deterministic backtesting with no randomness or execution model.

### Technology stack

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL 17, psycopg 3, pytest, Next.js 15, React 19, TypeScript 5.7+, Docker Compose.

### Honest limitations

- part of the frontend asset catalogue still uses demo fixtures;
- backtesting operates on a fixed deterministic demonstration series;
- commissions, spreads, taxes, liquidity, and corporate actions are not modelled;
- no authentication or multi-user authorization is implemented;
- no raw-facts explorer or full filings pagination metadata exists;
- live SEC access can be restricted, so official offline JSON import is supported;
- the project has not yet been deployed to a public production environment.

## Русский

### Короткое описание проекта

InvestScope — read-only платформа для исследования публичных компаний, объединяющая сохранённые рыночные данные, официальные SEC filings и нормализованные XBRL-факты. Она предоставляет point-in-time показатели, прозрачный аудит расчётов, аналитику вручную введённых позиций и детерминированное историческое тестирование сигналов без подключения к брокеру.

### Описание для резюме

Спроектировал и реализовал full-stack платформу инвестиционной аналитики на FastAPI, PostgreSQL, SQLAlchemy, Alembic, Next.js, React и TypeScript. Реализовал идемпотентный импорт рыночных и SEC-данных, детерминированный выбор XBRL-фактов, quarterly/annual/TTM расчёты, point-in-time анализ, полный provenance и адаптивный интерфейс; корректность подтверждается 133 backend-тестами и strict frontend-сборкой.

### Описание для GitHub

Read-only платформа исследования публичных компаний: SEC/XBRL ingestion, сохранённые рыночные данные, point-in-time фундаментальная аналитика, аудируемые расчётные метрики, анализ вручную введённого портфеля и детерминированный backtesting. Без брокерской интеграции и исполнения поручений.

### Engineering highlights

- независимые от провайдера контракты данных;
- UTC/Decimal-safe хранение в PostgreSQL;
- идемпотентная синхронизация и защита от дубликатов;
- общий throttling и дневные лимиты внешних API;
- транзакционный офлайн-импорт SEC JSON;
- обработка amendments, restatements и comparative facts;
- derived Q4, YTD differencing, TTM, ratios, growth и valuation;
- раздельные calculation components и полный source-fact audit trail;
- `as_of` семантика без использования будущих данных;
- корректная частичная оценка позиций без котировок;
- типизированные API и frontend-контракты;
- backtesting без случайных значений и модели исполнения сделок.

### Стек

Python 3.12+, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL 17, psycopg 3, pytest, Next.js 15, React 19, TypeScript 5.7+, Docker Compose.

### Честные ограничения

- часть каталога активов использует demo fixtures;
- backtesting работает на фиксированном демонстрационном ряду;
- не моделируются комиссии, спреды, налоги, ликвидность и корпоративные действия;
- отсутствуют аутентификация и multi-user authorization;
- нет raw facts explorer и полной pagination metadata для filings;
- live SEC доступ может ограничиваться, поэтому предусмотрен offline import;
- публичное production-развёртывание пока отсутствует.

## Product boundary

InvestScope provides research and educational analytics only. It is not investment advice, does not promise returns or forecast accuracy, and cannot execute real or simulated orders.
