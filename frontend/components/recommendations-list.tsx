"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { RatingBadge } from "@/components/ui";
import { formatApiError, listAssets, listRecommendations } from "@/lib/api";
import { formatMoney } from "@/lib/formatters";
import type { AssetListItem, DecimalJson, Rating, Recommendation } from "@/lib/types";

function decimalToNumber(value: DecimalJson | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function scoreWidth(score: DecimalJson): string {
  const parsed = decimalToNumber(score);
  if (parsed === null) return "0%";
  return `${Math.max(0, Math.min(100, parsed))}%`;
}

const ratingLabels: Record<Rating, string> = {
  BUY: "Положительных",
  HOLD: "Нейтральных",
  SELL: "Отрицательных",
};

export function RecommendationsList() {
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
  const counts = recommendations.reduce<Record<Rating, number>>(
    (accumulator, recommendation) => {
      accumulator[recommendation.rating] += 1;
      return accumulator;
    },
    { BUY: 0, HOLD: 0, SELL: 0 },
  );
  const latestCalculation = recommendations
    .map((recommendation) => recommendation.generated_at)
    .sort()
    .at(-1);

  if (loading) {
    return <p className="market-message">Загрузка аналитических рейтингов…</p>;
  }

  if (error) {
    return <p className="market-message error">{error}</p>;
  }

  if (!recommendations.length) {
    return (
      <>
        <section className="research-summary">
          <div><strong>0</strong><span>Активных рейтингов</span></div>
          <div><strong>0</strong><span>Положительных</span></div>
          <div><strong>0</strong><span>Нейтральных</span></div>
          <div><strong>0</strong><span>Отрицательных</span></div>
        </section>
        <div className="portfolio-empty-state">
          <span>Нет данных</span>
          <p>Аналитические рейтинги пока отсутствуют.</p>
        </div>
      </>
    );
  }

  return (
    <>
      <section className="research-summary">
        <div><strong>{recommendations.length}</strong><span>Активных рейтингов</span></div>
        {(["BUY", "HOLD", "SELL"] as const).map((rating) => (
          <div key={rating}><strong>{counts[rating]}</strong><span>{ratingLabels[rating]}</span></div>
        ))}
      </section>
      <section className="recommendation-list">
        {recommendations.map((recommendation, index) => {
          const asset = assetBySymbol.get(recommendation.symbol.toUpperCase());
          const quote = asset?.latest_quote ?? null;
          const price = decimalToNumber(quote?.close);
          const score = decimalToNumber(recommendation.score);
          return (
            <article className="panel recommendation-card" key={recommendation.symbol}>
              <div className="recommendation-rank">{String(index + 1).padStart(2, "0")}</div>
              <div className="recommendation-main">
                <div className="panel-heading">
                  <div>
                    <Link href={`/assets/${recommendation.symbol}`}>
                      <h2>{recommendation.symbol} <span>{asset?.name ?? "Актив из рейтинга"}</span></h2>
                    </Link>
                    <p>{asset?.sector ?? "Сектор не указан"} · Горизонт: {recommendation.horizon}</p>
                  </div>
                  <RatingBadge rating={recommendation.rating} />
                </div>
                <p className="rationale">{recommendation.rationale}</p>
                <div className="factor-bars">
                  <div>
                    <span>Сводная аналитическая оценка</span>
                    <i><b style={{ width: scoreWidth(recommendation.score) }} /></i>
                    <strong>{score === null ? "—" : score.toFixed(1)}</strong>
                  </div>
                  <div>
                    <span>Источник актива</span>
                    <i><b style={{ width: asset ? "100%" : "0%" }} /></i>
                    <strong>{asset ? "БД" : "—"}</strong>
                  </div>
                  <div>
                    <span>Рыночная цена</span>
                    <i><b style={{ width: quote ? "100%" : "0%" }} /></i>
                    <strong>{quote ? "Есть" : "Нет"}</strong>
                  </div>
                </div>
                <div className="rating-metadata">
                  <span>Дата расчёта: <strong>{formatDateTime(recommendation.generated_at)}</strong></span>
                  <span>Источник рейтинга: <strong>backend API</strong></span>
                  <span>Статус цены: <strong>{quote?.is_stale ? "Устарела" : quote ? "Актуальна" : "Нет данных"}</strong></span>
                </div>
              </div>
              <aside className="recommendation-price">
                <small>Текущая цена</small>
                <strong>{price === null || quote === null ? "Нет данных" : formatMoney(price, quote.currency)}</strong>
                <small>Источник цены</small>
                <strong>{quote?.source ?? "—"}</strong>
                <span>{quote?.received_at ? `Обновлено: ${formatDateTime(quote.received_at)}` : "Сохранённая котировка отсутствует"}</span>
              </aside>
            </article>
          );
        })}
      </section>
      <div className="method-note">
        <strong>Методика</strong>
        <p>
          Рейтинги и цены загружаются из backend API. Раздел является аналитическим и не создаёт торговые поручения
          или индивидуальные инвестиционные рекомендации.
          {latestCalculation ? ` Последний расчёт: ${formatDateTime(latestCalculation)} UTC.` : ""}
        </p>
      </div>
    </>
  );
}
