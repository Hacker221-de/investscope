"use client";

import { useEffect, useState } from "react";

import { fetchMarketApi } from "@/lib/api";
import type { ProviderMarketDataStatus } from "@/lib/types";

function utcTime(value: string | null): string {
  if (!value) return "Нет успешных обновлений";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short", timeStyle: "short", timeZone: "UTC",
  }).format(new Date(value)) + " UTC";
}

export function ProviderStatus() {
  const [status, setStatus] = useState<ProviderMarketDataStatus | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchMarketApi<ProviderMarketDataStatus>("/providers/market-data/status")
      .then(setStatus)
      .catch(() => setError(true));
  }, []);

  if (error) return <div className="market-message error">Не удалось получить статус источника.</div>;
  if (!status) return <div className="market-message">Загрузка статуса источника…</div>;
  const limited = status.daily_limit !== null && !status.available;

  return (
    <div className="provider-source-panel">
      <div className="source-status">
        <span className={`status-dot ${status.available ? "" : "unavailable"}`} />
        <div><strong>{status.configured_provider}</strong><small>Активный read-only провайдер</small></div>
        <em>{status.available ? "ДОСТУПЕН" : "ОГРАНИЧЕН"}</em>
      </div>
      <dl className="provider-usage-grid">
        <div><dt>Использовано сегодня</dt><dd>{status.requests_used_today}{status.daily_limit === null ? "" : ` / ${status.daily_limit}`}</dd></div>
        <div><dt>Осталось запросов</dt><dd>{status.remaining_requests ?? "Без лимита"}</dd></div>
        <div><dt>Последнее успешное обновление</dt><dd>{utcTime(status.last_success_at)}</dd></div>
        <div><dt>Freshness</dt><dd>{status.data_stale_after_hours} ч.</dd></div>
      </dl>
      {limited && <p className="provider-limit-message">Лимит запросов провайдера исчерпан или сохранён резерв.</p>}
      {status.last_error === "provider_burst_limit" && <p className="provider-limit-message">Действует временное ограничение частоты запросов.</p>}
      {status.last_error === "provider_daily_limit" && <p className="provider-limit-message">Доступный суточный бюджет запросов исчерпан.</p>}
      {status.last_error === "provider_rate_limit" && <p className="provider-limit-message">Провайдер вернул неопределённое ограничение запросов.</p>}
    </div>
  );
}
