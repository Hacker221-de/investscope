# InvestScope

InvestScope — аналитическое приложение для исследования активов и позиций, которые пользователь вводит вручную. Приложение не подключается к брокеру, не создаёт торговые поручения и не совершает сделки.

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

Локальные проверки:

```bash
cd backend
python -m pip install -e ".[dev]"
pytest
python -m alembic -c alembic.ini upgrade head --sql

cd ../frontend
npm install
npm run build
```

## Рыночные данные

`MarketDataProvider` отделяет аналитику и persistence от конкретного источника. Реализованы:

- `DemoMarketDataProvider` — детерминированные данные для разработки;
- `AlphaVantageMarketDataProvider` — внешний read-only источник Alpha Vantage.

Выбор источника:

```dotenv
INVESTSCOPE_MARKET_DATA_PROVIDER=alpha_vantage
INVESTSCOPE_ALPHA_VANTAGE_API_KEY=your-key
INVESTSCOPE_ALPHA_VANTAGE_BASE_URL=https://www.alphavantage.co/query
INVESTSCOPE_ALPHA_VANTAGE_DAILY_LIMIT=25
INVESTSCOPE_ALPHA_VANTAGE_DAILY_RESERVE=1
INVESTSCOPE_ALPHA_VANTAGE_MIN_INTERVAL_SECONDS=1.5
```

Ключ хранится только в окружении. Alpha Vantage free tier ограничен 25 запросами в день. `TIME_SERIES_DAILY` в режиме `compact` возвращает последние 100 наблюдений; полный ряд и adjusted daily data могут требовать premium-доступ. `GLOBAL_QUOTE` без premium-доступа обновляется в конце торгового дня. Подробнее: <https://www.alphavantage.co/documentation/> и <https://www.alphavantage.co/support/>.

Поддерживается таймфрейм `1d`. Alpha Vantage не сообщает точный `published_at` для каждой дневной строки, поэтому это поле остаётся `NULL`; `received_at` содержит фактическое UTC-время получения InvestScope. Значения `adjusted_close` также не подменяются обычным close.

## API рыночных данных

- `GET /api/assets`
- `GET /api/assets/{symbol}`
- `GET /api/market/{symbol}/history`
- `GET /api/market/{symbol}/latest`
- `POST /api/market/{symbol}/sync?start=2026-01-01&end=2026-06-30&timeframe=1d`

`POST sync` валидирует ASCII-тикер, запрещает будущие даты, ограничивает диапазон 366 днями и возвращает `inserted`, `updated`, `rejected`. Повторная синхронизация идемпотентна. Timeout, rate limit, неизвестный тикер и ошибка источника преобразуются в понятные HTTP-ответы. Endpoint только читает рыночные данные и записывает их в PostgreSQL.

`latest`, `history`, список Assets и Asset details по умолчанию читают бары только из `INVESTSCOPE_MARKET_DATA_PROVIDER`. Более новая запись другого источника не участвует в цене, предыдущем закрытии или графике. Для диагностического явного выбора поддерживается:

```text
GET /api/market/AAPL/latest?provider=demo
GET /api/market/AAPL/history?provider=alpha_vantage
```

Frontend не передаёт override и поэтому Assets, Asset Analysis и Portfolio всегда используют настроенный backend-провайдер.

Безопасная очистка demo-баров сначала работает как dry run:

```bash
python -m app.commands.market_data purge-demo-bars
python -m app.commands.market_data purge-demo-bars --confirm
```

Команда с `--confirm` удаляет только строки `market_bars` с точным `provider = 'demo'`. Assets, позиции и бары `alpha_vantage` не изменяются.

Котировка считается устаревшей, если `published_at` (или `event_time`, когда источник не сообщает время публикации) старше 36 часов. Порог задаётся `INVESTSCOPE_MARKET_DATA_STALE_AFTER_HOURS`.

### Защита лимита провайдера

Перед `POST /api/market/{symbol}/sync` проверяется последний сохранённый бар настроенного провайдера. Если `published_at` или, при его отсутствии, `event_time` моложе порога freshness, endpoint возвращает `skipped=true`, `reason=skip_reason="fresh_data"` и не вызывает provider.

Для Alpha Vantage каждый фактический HTTP-запрос записывается в `provider_request_logs`. Новая синхронизация существующего актива требует два запроса, нового актива — три; доступность всего request group проверяется заранее. Действуют следующие ограничения:

- каждый HTTP-вызов проходит через единый `AlphaVantageRequestGateway`;
- между началами отдельных вызовов выдерживается минимум 1,5 секунды по monotonic clock;
- общая async-блокировка сериализует задачи внутри процесса;
- PostgreSQL transaction-level advisory lock сериализует workers между процессами;
- дневной лимит задаётся `INVESTSCOPE_ALPHA_VANTAGE_DAILY_LIMIT`;
- один запрос по умолчанию сохраняется как резерв;
- после 429 автоматического retry нет, повтор блокируется до истечения `Retry-After` или настроенного cooldown;
- API-ключ остаётся только в backend environment и не записывается в логи или БД.

Статус без секретов доступен через:

```text
GET /api/providers/market-data/status
```

Он содержит настроенный provider, дневное использование, остаток, последние запрос/успех/ошибку и freshness threshold. Settings отображает эти данные, но не получает API-ключ. Синхронизация на Asset Analysis запускается только вручную.

Ответ при исчерпании бюджета или внешнем 429 имеет HTTP-код `429` и стабильную структуру `detail`. Технический текст провайдера и traceback клиенту не передаются.

Ошибки лимитов разделены: `provider_burst_limit` для краткосрочного 429, `provider_daily_limit` для дневного бюджета и `provider_rate_limit` только для неизвестного варианта. Если использовано меньше дневного лимита, API сообщает: «Действует временное ограничение частоты запросов».

Каждый реальный HTTP-вызов журналируется отдельно с `endpoint`, `requested_at`, `started_at`, `completed_at`, HTTP status, результатом, типом ошибки, `retry_after_seconds` и общим `request_group_id`. UTC используется только в журнале; продолжительность throttle рассчитывается через `time.monotonic()`.

Для `TIME_SERIES_DAILY` gateway применяет строгий внешний allowlist: `function`, `symbol`, `outputsize=compact`, `datatype=json` и `apikey`. `timeframe`, диапазон дат и служебные параметры InvestScope не передаются провайдеру; `start/end` фильтруются после получения дневного ряда. В безопасный application log попадают только function, symbol, outputsize и datatype. Ответ Alpha Vantage с `Error Message` преобразуется в HTTP 502 с `detail.code="provider_invalid_request"`.

## Инварианты хранения

- все `datetime` timezone-aware и нормализованы в UTC;
- цены и денежные значения в Python представлены `Decimal`, в PostgreSQL — `NUMERIC`;
- отсутствующие значения сохраняются как `NULL`, а не как нули;
- `volume >= 0`;
- `high >= open, close, low` и `low <= open, close, high` для присутствующих значений;
- уникальность бара: `asset_id + timeframe + event_time + provider`;
- некорректные строки отклоняются, учитываются в `rejected` и журналируются;
- данные будущего не принимаются sync endpoint.

## Portfolio

Раздел `/portfolio` анализирует фактически принадлежащие пользователю активы. Пользователь вводит `symbol`, `quantity`, `average_purchase_price`, `purchase_date`, `currency` и необязательную `fees`, либо импортирует CSV.

Текущая стоимость рассчитывается только по доступным сохранённым котировкам. Для каждой позиции показаны источник и UTC-время получения. Позиция без цены отмечается как неоценённая и исключается из суммарной доходности; количество таких позиций выводится отдельно.

## Оставшиеся демонстрационные данные

- справочник четырёх активов в UI до первой синхронизации;
- начальные вручную редактируемые позиции AAPL, MSFT и TLT в frontend;
- сводные цены на Dashboard и в карточках аналитических рейтингов;
- фундаментальные показатели, расчётная стоимость и аналитические рейтинги;
- политические события и новостное влияние;
- волатильность, просадка, корреляции и стресс-сценарии Portfolio;
- исторический ряд Backtesting;
- legacy endpoints `/api/v1/*` и manual position storage пока используют in-memory fixtures.

Демонстрационные цены больше не используются для текущей цены на страницах Assets, Asset Analysis и Portfolio. При отсутствии сохранённой котировки UI показывает «Нет данных» без ложного нуля.

## Ограничения

- нет аутентификации и фонового scheduler для синхронизации;
- нет конвертации валют портфеля;
- нет корпоративных действий и adjusted prices в бесплатной конфигурации Alpha Vantage;
- нет брокерских API, Buy/Sell, paper trading, поручений и автоматических сделок.
