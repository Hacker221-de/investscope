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

Свежесть дневной котировки разделена на два признака. `is_fetch_stale` сравнивает текущее время с фактическим `received_at`; порог задаётся `INVESTSCOPE_MARKET_DATA_STALE_AFTER_HOURS`. `is_market_data_stale` сравнивает дату бара с последней ожидаемой завершённой weekday-сессией. До настроенного закрытия (`INVESTSCOPE_MARKET_DAILY_SESSION_CLOSE_HOUR_UTC`, по умолчанию 21 UTC) ожидается предыдущий рабочий день, а в выходные — пятница. Поэтому `event_time=00:00 UTC` не делает свежий дневной бар устаревшим. Биржевые праздники пока не входят в базовый календарь.

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

## SEC EDGAR: фундаментальные данные

Фундаментальные данные загружаются только из официальных read-only JSON endpoints SEC:

- `https://www.sec.gov/files/company_tickers_exchange.json` — соответствие ticker/CIK;
- `https://data.sec.gov/submissions/CIK##########.json` — профиль и submissions;
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` — XBRL company facts.

SEC не требует API-ключ, но требует идентифицирующий `User-Agent`. Настройте `INVESTSCOPE_SEC_USER_AGENT` как название приложения и рабочий контакт. Он передаётся только SEC и не возвращается API/frontend. Единый `SecEdgarRequestGateway` использует общий async HTTP client, gzip, timeout и общий монотонный limiter для `www.sec.gov` и `data.sec.gov`. Консервативный предел по умолчанию — один запрос в секунду; параллельные задачи сериализуются async-lock, а PostgreSQL workers — transaction-level advisory lock. Автоматических retry после 403/429 нет.

Ticker→CIK хранится постоянно в PostgreSQL-таблице `sec_ticker_cache`, а не только в памяти процесса. TTL задаётся `INVESTSCOPE_SEC_TICKER_CACHE_TTL_HOURS` и по умолчанию равен 168 часам. Разрешение компании идёт в порядке: валидный `Asset.cik`, persistent ticker cache, внешний ticker index. Поэтому повторная синхронизация известного Asset не обращается к `company_tickers_exchange.json`. Если кеш устарел, а index отвечает rate-limit, timeout или временной сетевой ошибкой, используется последнее сохранённое значение и sync возвращает `warning="sec_ticker_cache_stale"`.

HTML-ответ SEC `Request Rate Threshold Exceeded`, `rate threshold` или `excessive requests` классифицируется как `sec_rate_limit`. Настоящий запрет, включая `Undeclared Automated Tool`, остаётся `sec_access_denied`. Остальные стабильные коды: `sec_company_not_found`, `sec_timeout`, `sec_invalid_response`, `sec_unavailable`. Сырой HTML SEC клиенту не передаётся.

API:

- `GET /api/fundamentals/{symbol}/profile`;
- `GET /api/fundamentals/{symbol}/filings` с фильтрами `form`, `filed_from`, `filed_to`, `as_of`, `limit`, `offset`;
- `GET /api/fundamentals/{symbol}/facts` с фильтрами `metric`, `taxonomy`, `form`, `fiscal_year`, `fiscal_period`, `as_of`, `limit`, `offset`;
- `POST /api/fundamentals/{symbol}/sync`.

Безопасный bootstrap известной компании:

```bash
python -m app.commands.fundamentals set-company --symbol AAPL --cik 0000320193 --name "Apple Inc." --exchange Nasdaq
```

Команда валидирует ASCII ticker, CIK ровно из десяти цифр и не перезаписывает конфликтующий CIK.

### Офлайн-импорт официальных SEC JSON

Если SEC отклоняет Python HTTP-клиент как `Undeclared Automated Tool`, InvestScope не пытается обходить access controls и не подменяет сетевую библиотеку. Официальные JSON-файлы, отдельно полученные пользователем из SEC endpoints `submissions` и `companyfacts`, можно безопасно импортировать локально:

```bash
python -m app.commands.fundamentals import-sec-json \
  --symbol AAPL \
  --submissions-file "/local/path/CIK0000320193-submissions.json" \
  --companyfacts-file "/local/path/CIK0000320193-companyfacts.json"
```

Импорт не выполняет сетевых запросов и не доступен через публичный HTTP API. Принимаются только существующие локальные файлы с расширением `.json`; URL запрещены. Каждый файл ограничен `INVESTSCOPE_SEC_IMPORT_MAX_FILE_MB` (100 MB по умолчанию), разбирается только как UTF-8 JSON и проверяется на структуру SEC. CIK нормализуется до десяти цифр и должен совпадать в обоих файлах и с сохранённым `Asset.cik`.

Profile, filings и facts сохраняются транзакционно и идемпотентно существующими SEC parsers и XBRL mapping. Amendments остаются отдельными revisions, отсутствующие facts учитываются в `facts_rejected`, отрицательные значения допустимы. `provider` остаётся `sec_edgar`; способ загрузки отражают `ingestion_method="manual_json"`, безопасное имя исходного файла и UTC-поле `imported_at`. Существующие GET endpoints работают с импортированными данными без отдельного режима.

Стабильные ошибки CLI: `sec_import_file_not_found`, `sec_import_file_too_large`, `sec_import_invalid_json`, `sec_import_invalid_submissions`, `sec_import_invalid_companyfacts`, `sec_import_cik_mismatch`, `sec_import_transaction_failed`. Полный финансовый JSON и локальные пути в журнал не записываются.

### Канонические фундаментальные метрики

`GET /api/fundamentals/{symbol}/metrics` строит вычисляемые временные ряды поверх неизменяемых raw facts. Параметры: `period_type=quarterly|annual|ttm`, timezone-aware `as_of`, `limit`, `offset`, `include_alternatives` и явный `annual_fallback`.

Канонический ключ состоит из asset, normalized metric, unit, фактических `period_start`/`period_end` и `period_type`. Fiscal year/period и SEC frame остаются provenance-полями и не определяют уникальность периода. Поэтому сравнительное значение за тот же экономический период из более позднего filing не создаёт новый квартал. Одинаковое значение помечается `repeated_comparative`; изменённое — `restated_value`; amendment становится выбранным только после своего `acceptance_datetime`. При нескольких concepts применяется порядок из централизованного XBRL mapping, а все кандидаты доступны через `alternative_facts`.

Для duration-метрик отсутствующий fiscal Q4 может быть восстановлен как `annual FY - Q1 - Q2 - Q3`, если financial year, единицы, периоды и concept semantics совместимы, а источники однозначны. Для cash-flow facts кварталы восстанавливаются из накопительных рядов: Q2 = 6M YTD − 3M YTD, Q3 = 9M YTD − 6M YTD, Q4 = FY − 9M YTD. Q2/Q3 не требуют появления 10-K; Q4 point-in-time становится доступен только после публикации соответствующего годового filing. Расчёт не создаёт `FinancialFact`: API возвращает `derived=true`, `selection_reason="derived_quarter"`, формулу, метод, confidence, warnings и все source facts.

TTM складывается только из четырёх неперекрывающихся последовательных канонических кварталов с одинаковой единицей и корректной fiscal sequence. Derived Q4 разрешён; YTD, annual и повторные comparative facts не считаются отдельными кварталами. При нехватке данных конкретная TTM-метрика получает `incomplete_ttm`; годовое значение допускается только с `annual_fallback=true`.

Вычисляются free cash flow, total debt, рост выручки/прибыли, маржи, current ratio, debt/equity, ROA, ROE и изменение числа акций. `PaymentsToAcquirePropertyPlantAndEquipment` хранится как опубликованный положительный расход, поэтому `FCF = OCF - capex`; знак raw fact глобально не меняется. Debt mapping включает `ShortTermBorrowings`, `CommercialPaper`, `LongTermDebtCurrent`, `CurrentPortionOfLongTermDebt`, `LongTermDebtNoncurrent` и `LongTermDebt`. Агрегированный `LongTermDebt` никогда не складывается одновременно с его current/noncurrent-компонентами. Missing values и нулевые/экономически некорректные знаменатели дают `null` и warning, а не искусственный ноль.

Market cap, P/E, P/S и P/FCF используют последнюю сохранённую цену настроенного market-data provider, у которой `event_time` и `received_at` не позднее `as_of`. P/E не рассчитывается при неположительной прибыли, остальные multiples — при отсутствующем числе акций или неположительном denominator. Устаревшая цена помечается `stale_market_price`.

На `/assets/[symbol]` раздел «Фундаментальный анализ» показывает квартальные, годовые и TTM-ряды, карточки, графики, баланс, маржи, акции/разводнение, multiples и таблицу provenance с fiscal label, календарными датами, SEC frame, filing, concept и ingestion method. Производный квартал явно помечается badge «Расчётное значение», пояснением, формулой и ссылками на использованные SEC filings; он не представляется как опубликованный SEC fact. Предусмотрены loading, error, empty и conflict/restatement states.

Поддерживаются формы `10-K`, `10-K/A`, `10-Q`, `10-Q/A`, `8-K`, `8-K/A`. Оригинал и amendment хранятся как разные accession revisions. Синхронизация транзакционна и идемпотентна; свежий `sec_last_synced_at` в пределах `INVESTSCOPE_SEC_CACHE_TTL_HOURS` предотвращает внешние запросы.

Централизованный XBRL mapping нормализует: revenue, gross profit, operating income, net income, basic/diluted EPS, operating cash flow, capital expenditures, cash, current assets/liabilities, total assets/liabilities, short/long-term debt, shareholders equity и shares outstanding. Исходные taxonomy/concept/unit всегда сохраняются. Instant, quarterly (70–110 дней), annual (330–380 дней), YTD и прочие duration facts разделяются по датам периода, а не только по форме отчёта. Отсутствующие значения отклоняются, не превращаются в нули; отрицательные финансовые значения допустимы.

Point-in-time запросы с `as_of` исключают filing до `acceptance_datetime` (или `filing_date`, если точное время отсутствует), fact после `filed_at`, а также amendment до момента его публикации. Это предотвращает использование будущей ревизии в историческом анализе.

Ограничения SEC/XBRL: значения отражают то, что эмитент подал в SEC; единицы, custom taxonomies и качество тегирования различаются. Нормализованный mapping не устраняет различия учётной политики. Исторические файлы submissions вне блока `recent` автоматически не загружаются. Автоматической консолидации дублирующих XBRL concepts в «единственное правильное» значение нет.

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
