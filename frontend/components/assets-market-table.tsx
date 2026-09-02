"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { formatApiError, listAssets } from "@/lib/api";
import { formatMoney } from "@/lib/formatters";
import type { AssetDataStatus, AssetListItem } from "@/lib/types";

const sectorLabel: Record<string, string> = {
  Technology: "Технологии",
  Semiconductors: "Полупроводники",
  "Fixed Income": "Облигации",
};

function assetTypeLabel(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized === "equity") return "Акция";
  if (normalized === "etf") return "Биржевой фонд";
  if (normalized === "bond") return "Облигация";
  if (normalized === "unknown") return "Не указан";
  return value;
}

function updatedAt(asset: AssetListItem): string {
  const value = asset.latest_quote?.received_at;
  return value ? new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value)) + " UTC" : "—";
}

function dataStatus(asset: AssetListItem): AssetDataStatus {
  return {
    has_latest_quote: asset.latest_quote !== null,
    is_fetch_stale: asset.latest_quote?.is_fetch_stale ?? false,
    is_market_data_stale: asset.latest_quote?.is_market_data_stale ?? false,
    source: asset.latest_quote?.source ?? null,
    received_at: asset.latest_quote?.received_at ?? null,
  };
}

export function AssetsMarketTable() {
  const [assets, setAssets] = useState<AssetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [assetType, setAssetType] = useState("all");
  const [sector, setSector] = useState("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    listAssets()
      .then((items) => { if (active) setAssets(items); })
      .catch((requestError) => {
        if (active) setError(formatApiError(requestError, "Не удалось загрузить активы."));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const assetTypes = useMemo(
    () => [...new Set(assets.map((asset) => asset.asset_type).filter(Boolean))].sort(),
    [assets],
  );
  const sectors = useMemo(
    () => [...new Set(assets.map((asset) => asset.sector).filter((value): value is string => Boolean(value)))].sort(),
    [assets],
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toUpperCase();
    return assets.filter((asset) => {
      const matchesQuery = !normalizedQuery
        || asset.symbol.includes(normalizedQuery)
        || asset.name.toUpperCase().includes(normalizedQuery);
      const matchesType = assetType === "all" || asset.asset_type === assetType;
      const matchesSector = sector === "all" || asset.sector === sector;
      return matchesQuery && matchesType && matchesSector;
    });
  }, [assetType, assets, query, sector]);

  return (
    <>
      <section className="toolbar panel">
        <label className="search-box">
          <span>⌕</span>
          <input
            aria-label="Поиск активов"
            placeholder="Тикер или название компании"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="Тип актива"
          value={assetType}
          onChange={(event) => setAssetType(event.target.value)}
        >
          <option value="all">Все типы активов</option>
          {assetTypes.map((item) => (
            <option key={item} value={item}>{assetTypeLabel(item)}</option>
          ))}
        </select>
        <select
          aria-label="Сектор"
          value={sector}
          onChange={(event) => setSector(event.target.value)}
        >
          <option value="all">Все секторы</option>
          {sectors.map((item) => (
            <option key={item} value={item}>{sectorLabel[item] ?? item}</option>
          ))}
        </select>
        <span className="result-count">
          {loading ? "Загрузка активов…" : `${filtered.length} из ${assets.length} активов`}
        </span>
      </section>

      {error && <p className="market-message error">{error}</p>}

      <section className="panel asset-table-panel">
        {loading ? (
          <p className="market-message">Загрузка активов…</p>
        ) : assets.length === 0 && !error ? (
          <div className="portfolio-empty-state">
            <span>Активы ещё не загружены</span>
            <p>Каталог появится после синхронизации или импорта активов в backend.</p>
          </div>
        ) : filtered.length === 0 ? (
          <p className="missing-value">Активы не найдены по заданному фильтру.</p>
        ) : (
          <div className="table-wrap">
            <table className="asset-table">
              <thead>
                <tr>
                  <th>Актив</th>
                  <th>Тип / сектор</th>
                  <th>Последняя цена</th>
                  <th>Изменение за день</th>
                  <th>Источник / обновление</th>
                  <th>Статус данных</th>
                  <th>Анализ</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((asset) => {
                  const quote = asset.latest_quote;
                  const price = quote ? Number(quote.close) : null;
                  const change = quote?.change_percent === null || quote?.change_percent === undefined
                    ? null
                    : Number(quote.change_percent);
                  const status = dataStatus(asset);
                  return (
                    <tr key={asset.id}>
                      <td>
                        <Link className="asset-symbol" href={`/assets/${asset.symbol}`}>
                          <span className="ticker-icon">{asset.symbol.slice(0, 1)}</span>
                          <span>
                            <strong>{asset.symbol}</strong>
                            <small>{asset.name}</small>
                          </span>
                        </Link>
                      </td>
                      <td>
                        <strong>{assetTypeLabel(asset.asset_type)}</strong>
                        <small className="cell-note">{sectorLabel[asset.sector ?? ""] ?? asset.sector ?? "Сектор не указан"}</small>
                      </td>
                      <td>
                        {price === null || !Number.isFinite(price)
                          ? <span className="missing-value">Нет данных</span>
                          : <strong>{formatMoney(price, quote?.currency ?? asset.currency)}</strong>}
                      </td>
                      <td className={change === null || !Number.isFinite(change) ? "" : change >= 0 ? "positive" : "negative"}>
                        {change === null || !Number.isFinite(change)
                          ? "—"
                          : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                      </td>
                      <td>
                        <span className="quote-source">
                          {status.source ?? "—"}
                          {status.is_fetch_stale && <em className="stale-badge">Давно загружено</em>}
                          {status.is_market_data_stale && <em className="stale-badge">Нет последней сессии</em>}
                        </span>
                        <small className="cell-note">{updatedAt(asset)}</small>
                      </td>
                      <td>{status.has_latest_quote ? "Есть сохранённая котировка" : "Котировка отсутствует"}</td>
                      <td><Link href={`/assets/${asset.symbol}`}>Открыть →</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
