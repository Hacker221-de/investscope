"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AssetMarketData } from "@/components/asset-market-data";
import { FundamentalAnalysis } from "@/components/fundamental-analysis";
import { CompanyProfileCard } from "@/components/fundamentals/company-profile-card";
import { SecFilingsTable } from "@/components/fundamentals/sec-filings-table";
import { MarketApiError, formatApiError, getAsset } from "@/lib/api";
import type { AssetDetail } from "@/lib/types";

export function AssetDetailsClient({ symbol }: { symbol: string }) {
  const normalizedSymbol = symbol.trim().toUpperCase();
  const [asset, setAsset] = useState<AssetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setNotFound(false);
    getAsset(normalizedSymbol)
      .then((value) => {
        if (active) setAsset(value);
      })
      .catch((requestError) => {
        if (!active) return;
        if (requestError instanceof MarketApiError && requestError.status === 404) {
          setNotFound(true);
          setAsset(null);
        } else {
          setError(formatApiError(requestError, "Не удалось загрузить актив."));
          setAsset(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [normalizedSymbol]);

  if (loading) {
    return (
      <section className="empty-state">
        <span>{normalizedSymbol}</span>
        <h1>Загрузка актива…</h1>
        <p>InvestScope получает карточку актива из backend API.</p>
      </section>
    );
  }

  if (notFound) {
    return (
      <section className="empty-state">
        <span>404</span>
        <h1>Актив не найден</h1>
        <p>Тикер {normalizedSymbol} отсутствует в базе данных InvestScope.</p>
        <Link href="/assets" className="primary-button">Вернуться к активам</Link>
      </section>
    );
  }

  if (error || !asset) {
    return (
      <section className="empty-state">
        <span>{normalizedSymbol}</span>
        <h1>Не удалось загрузить актив</h1>
        <p>{error || "Backend не вернул карточку актива."}</p>
        <Link href="/assets" className="primary-button">Вернуться к активам</Link>
      </section>
    );
  }

  return (
    <>
      <Link href="/assets" className="back-link">← Вернуться к активам</Link>
      <AssetMarketData asset={asset} />
      <CompanyProfileCard symbol={asset.symbol} />
      <FundamentalAnalysis symbol={asset.symbol} />
      <SecFilingsTable symbol={asset.symbol} />
    </>
  );
}
