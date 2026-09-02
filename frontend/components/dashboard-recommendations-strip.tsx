"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { RatingBadge } from "@/components/ui";
import { formatApiError, listAssets, listRecommendations } from "@/lib/api";
import { formatMoney } from "@/lib/formatters";
import type { AssetListItem, DecimalJson, Recommendation } from "@/lib/types";

function decimalToNumber(value: DecimalJson | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function DashboardRecommendationsStrip() {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [assets, setAssets] = useState<AssetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadRecommendations() {
      setLoading(true);
      setError("");
      try {
        const [nextRecommendations, nextAssets] = await Promise.all([
          listRecommendations(),
          listAssets(),
        ]);
        if (!active) return;
        setRecommendations(nextRecommendations);
        setAssets(nextAssets);
      } catch (requestError) {
        if (active) {
          setRecommendations([]);
          setAssets([]);
          setError(formatApiError(requestError));
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadRecommendations();
    return () => { active = false; };
  }, []);

  const assetBySymbol = useMemo(
    () => new Map(assets.map((asset) => [asset.symbol.toUpperCase(), asset])),
    [assets],
  );

  const visible = recommendations.slice(0, 3);

  return (
    <section className="panel recommendations-strip">
      <div>
        <p className="eyebrow">Последний расчёт</p>
        <h2>Аналитические рейтинги</h2>
      </div>
      {loading ? (
        <span className="mini-recommendation">Загрузка рейтингов…</span>
      ) : error ? (
        <span className="mini-recommendation">{error}</span>
      ) : visible.length ? (
        visible.map((recommendation) => {
          const asset = assetBySymbol.get(recommendation.symbol.toUpperCase());
          const quote = asset?.latest_quote ?? null;
          const price = decimalToNumber(quote?.close);
          return (
            <Link
              href={`/assets/${recommendation.symbol}`}
              className="mini-recommendation"
              key={recommendation.symbol}
            >
              <span>
                <strong>{recommendation.symbol}</strong>
                <small>
                  {price === null || quote === null
                    ? asset?.name ?? "Нет сохранённой цены"
                    : `${asset?.name ?? "Цена"} · ${formatMoney(price, quote.currency)}`}
                </small>
              </span>
              <RatingBadge rating={recommendation.rating} />
            </Link>
          );
        })
      ) : (
        <span className="mini-recommendation">Рейтинги пока отсутствуют.</span>
      )}
      <Link href="/recommendations" className="text-link">Все рейтинги →</Link>
    </section>
  );
}
