"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAssetHistory,
  getAssetLatestMarketData,
  fetchMarketApi,
  MarketApiError,
} from "@/lib/api";
import { formatMoney } from "@/lib/formatters";
import type { AssetDetail, MarketBar, MarketQuote, MarketSyncResult } from "@/lib/types";

function chartPoints(values: number[]): string {
  if (values.length === 0) return "";
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  return values.map((value, index) => {
    const x = values.length === 1 ? 310 : index / (values.length - 1) * 620;
    const y = 165 - (value - minimum) / range * 145;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function assetTypeLabel(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized === "equity") return "Акция";
  if (normalized === "etf") return "Биржевой фонд";
  if (normalized === "bond") return "Облигация";
  if (normalized === "unknown") return "Тип не указан";
  return value;
}

function marketErrorMessage(error: unknown): string {
  if (error instanceof MarketApiError) {
    if (typeof error.detail === "string" && error.detail.trim()) return error.detail;
    if (error.detail && typeof error.detail === "object") {
      const detail = error.detail as { message?: unknown; code?: unknown };
      if (typeof detail.message === "string") return detail.message;
      if (typeof detail.code === "string") return detail.code;
    }
    return `Ошибка рыночных данных (HTTP ${error.status})`;
  }
  return error instanceof Error && error.message
    ? error.message
    : "Не удалось загрузить сохранённые рыночные данные.";
}

export function AssetMarketData({ asset }: { asset: AssetDetail }) {
  const [quote, setQuote] = useState<MarketQuote | null>(asset.latest_quote);
  const [bars, setBars] = useState<MarketBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [syncError, setSyncError] = useState(false);

  const loadData = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [latest, history] = await Promise.all([
        getAssetLatestMarketData(asset.symbol).catch((requestError) => {
          if (requestError instanceof MarketApiError && requestError.status === 404) return null;
          throw requestError;
        }),
        getAssetHistory(asset.symbol).catch((requestError) => {
          if (requestError instanceof MarketApiError && requestError.status === 404) {
            return { symbol: asset.symbol, timeframe: "1d", provider: "", bars: [] };
          }
          throw requestError;
        }),
      ]);
      setQuote(latest?.quote ?? null);
      setBars(history.bars);
    } catch (requestError) {
      setError(marketErrorMessage(requestError));
      setQuote(asset.latest_quote);
      setBars([]);
    } finally {
      setLoading(false);
    }
  }, [asset]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function synchronize() {
    setSyncing(true);
    setSyncMessage("");
    setSyncError(false);
    try {
      const result = await fetchMarketApi<MarketSyncResult>(
        `/market/${asset.symbol}/sync`,
        { method: "POST" },
      );
      if (result.skipped && result.skip_reason === "fresh_data") {
        setSyncMessage("Используются свежие сохранённые данные");
      } else {
        setSyncMessage(`Обновление завершено: добавлено ${result.inserted}, обновлено ${result.updated}.`);
        await loadData();
      }
    } catch (requestError) {
      setSyncError(true);
      if (requestError instanceof MarketApiError && requestError.status === 429) {
        const detail = requestError.detail as { message?: string; retry_after_seconds?: number | null };
        const retry = detail?.retry_after_seconds
          ? ` Повторите не ранее чем через ${detail.retry_after_seconds} сек.`
          : "";
        setSyncMessage(`${detail?.message ?? "Провайдер временно ограничил запросы"}.${retry}`);
      } else {
        setSyncMessage("Не удалось обновить данные. Сохранённые котировки остаются доступными.");
      }
    } finally {
      setSyncing(false);
    }
  }

  const closes = useMemo(() => (
    bars.flatMap((bar) => {
      if (bar.close === null) return [];
      const value = Number(bar.close);
      return Number.isFinite(value) ? [value] : [];
    })
  ), [bars]);
  const points = chartPoints(closes);
  const change = quote?.change_percent === null || quote?.change_percent === undefined
    ? null
    : Number(quote.change_percent);
  const updateValue = quote?.received_at;
  const updated = updateValue ? new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(updateValue)) + " UTC" : null;
  const quotePrice = quote ? Number(quote.close) : null;

  return (
    <>
      <header className="asset-header">
        <div className="ticker-icon large">{asset.symbol.slice(0, 1)}</div>
        <div>
          <p className="eyebrow">{assetTypeLabel(asset.asset_type)}</p>
          <h1>{asset.symbol} <span>{asset.name}</span></h1>
          <p>
            {quote ? (
              <>
                Источник: {quote.source} · Загружено: {updated}
                {quote.is_fetch_stale && <em className="stale-badge">Давно загружено</em>}
                {quote.is_market_data_stale && <em className="stale-badge">Нет последней завершённой сессии</em>}
              </>
            ) : loading ? (
              "Загрузка сохранённой котировки…"
            ) : (
              "Сохранённая котировка отсутствует"
            )}
          </p>
        </div>
        <div className="asset-quote">
          {quote && quotePrice !== null && Number.isFinite(quotePrice) ? (
            <>
              <strong>{formatMoney(quotePrice, quote.currency)}</strong>
              <span className={change === null || !Number.isFinite(change) ? "" : change >= 0 ? "positive" : "negative"}>
                {change === null || !Number.isFinite(change)
                  ? "Нет предыдущего закрытия"
                  : `${change >= 0 ? "+" : ""}${change.toFixed(2)}% к предыдущему закрытию`}
              </span>
            </>
          ) : (
            <strong className="missing-value">Нет данных</strong>
          )}
          <button
            className="secondary-button quote-sync-button"
            type="button"
            disabled={syncing}
            onClick={synchronize}
          >
            {syncing ? "Проверка…" : "Обновить данные"}
          </button>
        </div>
      </header>
      {syncMessage && <p className={`market-message ${syncError ? "error" : ""}`} role="status">{syncMessage}</p>}
      {error && <p className="market-message error">{error}</p>}
      <article className="panel asset-profile-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">Паспорт актива</p><h2>Данные из backend</h2></div>
          <span className="timestamp">ID {asset.id}</span>
        </div>
        <dl className="system-grid">
          <div><dt>Биржа</dt><dd>{asset.exchange ?? "—"}</dd></div>
          <div><dt>Сектор</dt><dd>{asset.sector ?? "—"}</dd></div>
          <div><dt>Индустрия</dt><dd>{asset.industry ?? "—"}</dd></div>
          <div><dt>Валюта</dt><dd>{asset.currency}</dd></div>
          <div><dt>Provider symbol</dt><dd>{asset.provider_symbol ?? "—"}</dd></div>
          <div><dt>Активен</dt><dd>{asset.is_active ? "Да" : "Нет"}</dd></div>
        </dl>
      </article>
      <article className="panel chart-panel market-history">
        <div className="panel-heading">
          <div><p className="eyebrow">История цены</p><h2>Сохранённые дневные закрытия</h2></div>
          <span className="timestamp">{loading ? "Загрузка…" : `${bars.length} наблюдений`}</span>
        </div>
        {points ? (
          <>
            <svg className="main-chart asset-chart" viewBox="0 0 620 180" preserveAspectRatio="none" role="img" aria-label="График истории цены">
              <polyline points={points} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="chart-axis"><span>{bars[0]?.event_time.slice(0, 10)}</span><span>{bars.at(-1)?.event_time.slice(0, 10)}</span></div>
          </>
        ) : (
          <div className="chart-empty">Исторические данные отсутствуют.</div>
        )}
      </article>
    </>
  );
}
