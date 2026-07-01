"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RatingBadge, Sparkline } from "@/components/ui";
import { fetchMarketApi } from "@/lib/api";
import { currency } from "@/lib/demo-data";
import type { Asset, MarketAsset } from "@/lib/types";

const typeLabel = { Equity: "Акция", ETF: "Биржевой фонд" } as const;
const sectorLabel: Record<string, string> = {
  Technology: "Технологии",
  Semiconductors: "Полупроводники",
  "Fixed Income": "Облигации",
};

function updatedAt(asset: MarketAsset | undefined): string {
  const value = asset?.latest_quote?.received_at;
  return value ? new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short", timeStyle: "short", timeZone: "UTC",
  }).format(new Date(value)) + " UTC" : "—";
}

export function AssetsMarketTable({ fixtures }: { fixtures: Asset[] }) {
  const [stored, setStored] = useState<MarketAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchMarketApi<MarketAsset[]>("/assets")
      .then(setStored)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const bySymbol = new Map(stored.map((asset) => [asset.symbol, asset]));
  return (
    <>
      {error && <p className="market-message error">Не удалось загрузить сохранённые рыночные данные.</p>}
      <section className="panel asset-table-panel">
        <div className="table-wrap"><table className="asset-table"><thead><tr><th>Актив</th><th>Тип / сектор</th><th>Последняя цена</th><th>Изменение за день</th><th>Источник / обновление</th><th>Расчётная стоимость</th><th>Аналитический рейтинг</th></tr></thead><tbody>
          {fixtures.map((asset) => {
            const marketAsset = bySymbol.get(asset.symbol);
            const quote = marketAsset?.latest_quote;
            const price = quote ? Number(quote.close) : null;
            const change = quote?.change_percent === null || quote?.change_percent === undefined
              ? null : Number(quote.change_percent);
            return <tr key={asset.symbol}><td><Link className="asset-symbol" href={`/assets/${asset.symbol}`}><span className="ticker-icon">{asset.symbol.slice(0, 1)}</span><span><strong>{asset.symbol}</strong><small>{marketAsset?.name ?? asset.name}</small></span></Link></td><td><strong>{typeLabel[asset.type]}</strong><small className="cell-note">{sectorLabel[marketAsset?.sector ?? asset.sector] ?? marketAsset?.sector ?? asset.sector}</small></td><td>{price === null ? <span className="missing-value">{loading ? "Загрузка…" : "Нет данных"}</span> : <strong>{currency.format(price)}</strong>}</td><td className={change === null ? "" : change >= 0 ? "positive" : "negative"}>{change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}</td><td><span className="quote-source">{quote?.source ?? "—"}{quote?.is_fetch_stale && <em className="stale-badge">Давно загружено</em>}{quote?.is_market_data_stale && <em className="stale-badge">Нет последней сессии</em>}</span><small className="cell-note">{updatedAt(marketAsset)}</small></td><td>{currency.format(asset.fairValue)}<small className="cell-note">Демо-модель</small></td><td><RatingBadge rating={asset.rating}/></td></tr>;
          })}
        </tbody></table></div>
      </section>
    </>
  );
}
