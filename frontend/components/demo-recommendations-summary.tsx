"use client";

import { useEffect, useState } from "react";

import { MetricCard } from "@/components/ui";
import { formatApiError, listRecommendations } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export function DemoRecommendationsSummary() {
  const [recommendations, setRecommendations] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    listRecommendations().then(
      (data) => { if (active) setRecommendations(data); },
      (requestError: unknown) => { if (active) setError(formatApiError(requestError)); },
    );
    return () => { active = false; };
  }, []);

  const counts = recommendations?.reduce(
    (result, recommendation) => {
      result[recommendation.rating] += 1;
      return result;
    },
    { BUY: 0, HOLD: 0, SELL: 0 },
  );

  return (
    <MetricCard
      label="Демонстрационные рейтинги"
      value={error ? "Нет данных" : recommendations ? String(recommendations.length) : "Загрузка…"}
      detail={error || (counts
        ? `Положительных: ${counts.BUY} · Нейтральных: ${counts.HOLD} · Отрицательных: ${counts.SELL}`
        : "Демо · Фиксированные примеры")}
    />
  );
}
