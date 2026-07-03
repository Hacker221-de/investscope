# InvestScope

InvestScope — аналитическая платформа для исследования публичных компаний. Она объединяет сохранённые рыночные данные, официальные SEC filings и XBRL-факты, рассчитывает квартальные, годовые и TTM-показатели и сохраняет полный аудит источников.

Приложение работает только в read-only аналитическом режиме: не подключается к брокерам, не исполняет реальные или виртуальные поручения и не формирует персональные инвестиционные рекомендации.

## Основные возможности

- ручной офлайн-импорт официальных SEC submissions/companyfacts JSON;
- нормализация XBRL с сохранением исходного concept, taxonomy и unit;
- point-in-time анализ через `as_of`;
- детерминированный выбор канонического факта;
- учёт comparative-фактов, amendments и restatements;
- отдельные `calculation_components` и полный `source_facts` audit trail;
- хранение дневных рыночных данных в PostgreSQL;
- аналитика вручную введённых позиций без торговых функций;
- историческое тестирование аналитических сигналов на фиксированном демонстрационном ряду;
- адаптивный frontend на Next.js.

## Быстрый запуск

```powershell
Copy-Item .env.example .env
Copy-Item frontend/.env.example frontend/.env.local
docker compose up --build
```

После запуска:

- приложение: <http://localhost:3000>;
- API: <http://localhost:8000>;
- OpenAPI: <http://localhost:8000/docs>.

Подробные инструкции, архитектура, импорт SEC JSON, тестирование и ограничения описаны в [README.md](README.md) и [docs/architecture.md](docs/architecture.md).

## Проверки

- backend pytest: 133 passed;
- `npm run typecheck`: passed;
- `npm run build`: passed;
- URL tests: 3 passed.

## Ограничения

Часть каталога активов всё ещё использует демонстрационные данные. Backtesting не учитывает комиссии, спреды, налоги, ликвидность и корпоративные действия. Публичное production-развёртывание, raw facts explorer и полноценная pagination metadata для filings пока отсутствуют.

## Дисклеймер

Только исследовательская и образовательная аналитика. Не является инвестиционной рекомендацией. Сделки и торговые поручения не выполняются.
