"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchMarketApi, MarketApiError } from "@/lib/api";
import { currency } from "@/lib/demo-data";
import type { Asset, MarketBar, MarketQuote, MarketSyncResult } from "@/lib/types";

interface LatestResponse { symbol: string; quote: MarketQuote }
interface HistoryResponse { symbol: string; timeframe: string; bars: MarketBar[] }

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

export function AssetMarketData({ asset }: { asset: Asset }) {
  const [quote, setQuote] = useState<MarketQuote | null>(null);
  const [bars, setBars] = useState<MarketBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const [syncError, setSyncError] = useState(false);

  const loadData = useCallback(async () => {
    setError(false);
    setLoading(true);
    await Promise.all([
      fetchMarketApi<LatestResponse>(`/market/${asset.symbol}/latest`),
      fetchMarketApi<HistoryResponse>(`/market/${asset.symbol}/history`),
    ]).then(([latest, history]) => {
      setQuote(latest.quote);
      setBars(history.bars);
    }).catch(() => setError(true)).finally(() => setLoading(false));
  }, [asset.symbol]);

  useEffect(() => { void loadData(); }, [loadData]);

  async function synchronize() {
    setSyncing(true);
    setSyncMessage("");
    setSyncError(false);
    try {
      const result = await fetchMarketApi<MarketSyncResult>(
        `/market/${asset.symbol}/sync`, { method: "POST" },
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
          ? ` Повторите не ранее чем через ${detail.retry_after_seconds} сек.` : "";
        setSyncMessage(`${detail?.message ?? "Лимит запросов провайдера исчерпан"}.${retry}`);
      } else {
        setSyncMessage("Не удалось обновить данные. Сохранённые котировки остаются доступными.");
      }
    } finally {
      setSyncing(false);
    }
  }

  const closes = useMemo(() => bars.flatMap((bar) => bar.close === null ? [] : [Number(bar.close)]), [bars]);
  const points = chartPoints(closes);
  const change = quote?.change_percent === null || quote?.change_percent === undefined
    ? null : Number(quote.change_percent);
  const updateValue = quote?.received_at;
  const updated = updateValue ? new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  }).format(new Date(updateValue)) + " UTC" : null;

  return (
    <>
      <header className="asset-header">
        <div className="ticker-icon large">{asset.symbol.slice(0, 1)}</div>
        <div><p className="eyebrow">{asset.type === "Equity" ? "Акция" : "Биржевой фонд"}</p><h1>{asset.symbol} <span>{asset.name}</span></h1><p>{quote ? <>Источник: {quote.source} · Загружено: {updated}{quote.is_fetch_stale && <em className="stale-badge">Давно загружено</em>}{quote.is_market_data_stale && <em className="stale-badge">Нет последней завершённой сессии</em>}</> : loading ? "Загрузка сохранённой котировки…" : "Сохранённая котировка отсутствует"}</p></div>
        <div className="asset-quote">{quote ? <><strong>{currency.format(Number(quote.close))}</strong><span className={change === null ? "" : change >= 0 ? "positive" : "negative"}>{change === null ? "Нет предыдущего закрытия" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}% к предыдущему закрытию`}</span></> : <strong className="missing-value">Нет данных</strong>}<button className="secondary-button quote-sync-button" type="button" disabled={syncing} onClick={synchronize}>{syncing ? "Проверка…" : "Обновить данные"}</button></div>
      </header>
      {syncMessage && <p className={`market-message ${syncError ? "error" : ""}`} role="status">{syncMessage}</p>}
      {error && <p className="market-message error">Нет сохранённых цен. Выполните синхронизацию рыночных данных через API.</p>}
      <article className="panel chart-panel market-history"><div className="panel-heading"><div><p className="eyebrow">История цены</p><h2>Сохранённые дневные закрытия</h2></div><span className="timestamp">{bars.length} наблюдений</span></div>{points ? <><svg className="main-chart asset-chart" viewBox="0 0 620 180" preserveAspectRatio="none" role="img" aria-label="График истории цены"><polyline points={points} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke"/></svg><div className="chart-axis"><span>{bars[0]?.event_time.slice(0, 10)}</span><span>{bars.at(-1)?.event_time.slice(0, 10)}</span></div></> : <div className="chart-empty">Исторические данные отсутствуют.</div>}</article>
    </>
  );
}
