# InvestScope

InvestScope — каркас веб-приложения для инвестиционных исследований и анализа активов, которыми пользователь фактически владеет и вводит вручную.

> InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки.

## Стек

- frontend: Next.js 15, React 19, TypeScript;
- backend: Python 3.12+, FastAPI, Pydantic;
- database: PostgreSQL 17, SQLAlchemy 2, Alembic;
- tests: pytest;
- deployment: Docker Compose.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

- UI: <http://localhost:3000>
- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- health: <http://localhost:8000/health>

Локальный backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
uvicorn app.main:app --reload
```

Локальный frontend:

```bash
cd frontend
npm install
npm run build
npm run dev
```

## Структура

```text
investscope/
├── backend/
│   ├── alembic/                 # схема PostgreSQL
│   ├── app/
│   │   ├── api/                 # FastAPI routes
│   │   ├── core/                # settings, database, UTC helpers
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic contracts
│   │   ├── modules/portfolio/   # owned-position analytics
│   │   └── demo_data.py         # deterministic market fixtures
│   └── tests/
├── frontend/
│   ├── app/portfolio/           # portfolio analysis page
│   ├── components/portfolio-manager.tsx
│   └── lib/
├── AGENTS.md
└── docker-compose.yml
```

## Portfolio

Раздел `/portfolio` предназначен для учёта фактически принадлежащих пользователю активов. Для позиции указываются:

- `symbol`;
- `quantity`;
- `average_purchase_price`;
- `purchase_date`;
- `currency`;
- `fees` — необязательно.

Доступны добавление, изменение и удаление позиций, а также импорт UTF-8 CSV. Заголовок CSV:

```csv
symbol,quantity,average_purchase_price,purchase_date,currency,fees
AAPL,10,185.25,2025-04-12,USD,4.50
```

Аналитический ответ содержит текущую стоимость, вложенный капитал, нереализованный результат, доходность, распределения по активам/секторам/валютам, концентрацию, волатильность, максимальную просадку, корреляции, политические и географические риски, стресс-сценарии и влияние новостей.

## API

- `GET /health`
- `GET /api/v1/dashboard`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{symbol}`
- `GET /api/v1/recommendations`
- `GET /api/v1/portfolio`
- `POST /api/v1/portfolio/positions`
- `PATCH /api/v1/portfolio/positions/{position_id}`
- `DELETE /api/v1/portfolio/positions/{position_id}`
- `POST /api/v1/portfolio/import-csv`
- `GET /api/v1/political-events`
- `POST /api/v1/backtesting/run`

API не содержит методов создания торговых поручений или исполнения сделок.

## Инварианты данных

- Все `datetime` содержат timezone и нормализуются в UTC.
- `purchase_date` хранится как календарная SQL `DATE`, без неоднозначности часового пояса.
- Денежные значения и количества в Python используют `Decimal`, в PostgreSQL — `NUMERIC`.
- Позиция хранит данные пользователя; текущая цена и аналитические атрибуты присоединяются отдельно.
- Строгая типизация включена для Python-контрактов и TypeScript.

## Тесты

```bash
cd backend
pytest
```

Проверяются health endpoint, ручной CRUD позиций, CSV-импорт, UTC, Decimal-арифметика и все основные аналитические блоки Portfolio.

## Ограничения

- Рыночные цены, новости, события, коэффициенты корреляции и исторические ряды пока демонстрационные.
- API хранит изменения позиций в памяти процесса; SQLAlchemy-модели и миграция подготовлены для подключения постоянного repository-слоя.
- Аналитика поддерживает только символы, присутствующие в текущем демонстрационном справочнике активов.
- Пересчёт валют в базовую валюту пока не реализован.
- Нет аутентификации, ролей, фоновых задач, кэша и rate limiting.
- Стресс-тесты и новостное влияние являются прозрачными сценариями, а не прогнозом.
- Приложение не интегрируется с брокерами, биржами или системами исполнения сделок.
