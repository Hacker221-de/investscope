"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { MetricCard } from "@/components/ui";
import { fetchMarketApi, formatApiError, getPortfolio, listPortfolios } from "@/lib/api";
import type { DecimalJson, MarketAsset, PortfolioDetail, Position } from "@/lib/types";

interface DashboardPortfolioSummaryProps {
  eventPanel: ReactNode;
}

type DashboardPosition = Position & {
  asset?: MarketAsset;
  quantityNumber: number | null;
  averagePurchasePriceNumber: number | null;
  currentPrice?: number;
  currentValue?: number;
  investedCapital?: number;
  pnl?: number;
  weight?: number;
};

function decimalToNumber(value: DecimalJson | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number, currencyCode = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode,
      currencyDisplay: "code",
      minimumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currencyCode} ${value.toFixed(2)}`;
  }
}

export function DashboardPortfolioSummary({ eventPanel }: DashboardPortfolioSummaryProps) {
  const [portfolio, setPortfolio] = useState<PortfolioDetail | null>(null);
  const [marketAssets, setMarketAssets] = useState<MarketAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function loadSummary() {
      setLoading(true);
      setError("");
      try {
        const [portfolioList, assetList] = await Promise.all([
          listPortfolios(),
          fetchMarketApi<MarketAsset[]>("/assets"),
        ]);
        if (!active) return;
        setMarketAssets(assetList);
        if (!portfolioList.length) {
          setPortfolio(null);
          return;
        }
        const detail = await getPortfolio(portfolioList[0].id);
        if (active) setPortfolio(detail);
      } catch (requestError) {
        if (active) {
          setPortfolio(null);
          setError(formatApiError(requestError));
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadSummary();
    return () => { active = false; };
  }, []);

  const assetById = useMemo(
    () => new Map(marketAssets.map((asset) => [asset.id, asset])),
    [marketAssets],
  );

  const evaluated: DashboardPosition[] = useMemo(() => (
    (portfolio?.positions ?? []).map((position) => {
      const asset = assetById.get(position.asset_id);
      const quote = asset?.latest_quote ?? null;
      const quantity = decimalToNumber(position.quantity);
      const averagePurchasePrice = decimalToNumber(position.average_purchase_price);
      const fees = decimalToNumber(position.fees) ?? 0;
      const currentPrice = quote ? decimalToNumber(quote.close) : null;
      const investedCapital = quantity !== null && averagePurchasePrice !== null
        ? quantity * averagePurchasePrice + fees
        : undefined;
      const currentValue = quantity !== null && currentPrice !== null
        ? quantity * currentPrice
        : undefined;
      return {
        ...position,
        asset,
        quantityNumber: quantity,
        averagePurchasePriceNumber: averagePurchasePrice,
        currentPrice: currentPrice ?? undefined,
        currentValue,
        investedCapital,
        pnl: currentValue !== undefined && investedCapital !== undefined
          ? currentValue - investedCapital
          : undefined,
      };
    })
  ), [assetById, portfolio]);

  const valued = evaluated.filter((position) => position.currentValue !== undefined);
  const currentValue = valued.reduce((sum, position) => sum + (position.currentValue ?? 0), 0);
  const investedCapital = valued.reduce((sum, position) => sum + (position.investedCapital ?? 0), 0);
  const unrealizedPnl = currentValue - investedCapital;
  const totalReturn = investedCapital > 0 ? unrealizedPnl / investedCapital * 100 : null;
  const baseCurrency = portfolio?.base_currency ?? "USD";
  const withWeights = evaluated.map((position) => ({
    ...position,
    weight: position.currentValue !== undefined && currentValue > 0
      ? position.currentValue / currentValue * 100
      : undefined,
  }));
  const largestPositions = [...withWeights]
    .filter((position) => position.currentValue !== undefined)
    .sort((first, second) => (second.currentValue ?? 0) - (first.currentValue ?? 0))
    .slice(0, 5);

  const sectorAllocation = new Map<string, number>();
  valued.forEach((position) => {
    const label = position.asset?.sector ?? "Не указан";
    sectorAllocation.set(label, (sectorAllocation.get(label) ?? 0) + (position.currentValue ?? 0));
  });
  const sectorItems = [...sectorAllocation.entries()]
    .map(([label, value]) => [label, currentValue > 0 ? value / currentValue * 100 : 0] as const)
    .sort((first, second) => second[1] - first[1]);

  const summaryText = loading
    ? "Загрузка портфеля…"
    : error
      ? "Не удалось загрузить портфель"
      : portfolio
        ? "По сохранённым позициям"
        : "Портфели ещё не созданы";

  return (
    <>
      {error && <p className="market-message error">{error}</p>}

      <section className="metrics-grid" aria-label="Показатели портфеля">
        <MetricCard
          label="Текущая стоимость портфеля"
          value={valued.length ? money(currentValue, baseCurrency) : "Нет данных"}
          detail={summaryText}
        />
        <MetricCard
          label="Вложенный капитал"
          value={valued.length ? money(investedCapital, baseCurrency) : "Нет данных"}
          detail="Неоценённые позиции исключены"
        />
        <MetricCard
          label="Нереализованная прибыль / убыток"
          value={valued.length ? `${unrealizedPnl >= 0 ? "+" : ""}${money(unrealizedPnl, baseCurrency)}` : "Нет данных"}
          detail={totalReturn === null ? "Нет оценённых позиций" : `Доходность: ${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`}
          tone={valued.length ? unrealizedPnl >= 0 ? "positive" : "negative" : undefined}
        />
        <MetricCard label="Аналитические рейтинги" value="3 активных" detail="2 положительных · 1 нейтральный" />
      </section>

      <section className="dashboard-grid">
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Введённые позиции</p><h2>Оценка портфеля</h2></div>
            <Link href="/portfolio">Открыть портфель →</Link>
          </div>
          <div className="chart-value">
            <strong>{totalReturn === null ? "Нет данных" : `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`}</strong>
            <span>{valued.length ? `оценено позиций: ${valued.length}` : "нужны сохранённые котировки"}</span>
          </div>
          <p className="missing-value">
            Историческая динамика портфеля не строится из demo-ряда; она будет доступна после появления сохранённой истории стоимости портфеля.
          </p>
        </article>

        <article className="panel allocation-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Распределение</p><h2>Структура портфеля</h2></div>
          </div>
          <div className="donut" aria-label="Распределение портфеля">
            <span>
              <strong>{withWeights.some((position) => position.weight !== undefined)
                ? `${Math.max(...withWeights.map((position) => position.weight ?? 0)).toFixed(1)}%`
                : "—"}</strong>
              <small>крупнейшая позиция</small>
            </span>
          </div>
          {sectorItems.length ? (
            <ul className="legend">
              {sectorItems.slice(0, 3).map(([label, value], index) => (
                <li key={label}>
                  <i className={index === 0 ? "teal" : "blue"} />
                  {label} <strong>{value.toFixed(1)}%</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="missing-value">Нет оценённых позиций.</p>
          )}
        </article>
      </section>

      <section className="dashboard-grid lower-grid">
        <article className="panel wide-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Состав портфеля</p><h2>Крупнейшие позиции</h2></div>
            <Link href="/portfolio">Открыть портфель →</Link>
          </div>
          <div className="table-wrap">
            <table className="sticky-ticker">
              <thead>
                <tr>
                  <th>Актив</th>
                  <th>Цена</th>
                  <th>Текущая стоимость</th>
                  <th>Источник</th>
                  <th>Нереализованная прибыль / убыток</th>
                </tr>
              </thead>
              <tbody>
                {largestPositions.length ? largestPositions.map((position) => (
                  <tr key={position.id}>
                    <td>
                      <Link className="asset-symbol" href={`/assets/${position.symbol}`}>
                        <strong>{position.symbol}</strong>
                        <small>{position.asset?.name ?? "Сохранённый актив"}</small>
                      </Link>
                    </td>
                    <td>{position.currentPrice === undefined ? "—" : money(position.currentPrice, position.asset?.latest_quote?.currency ?? position.currency)}</td>
                    <td>{position.currentValue === undefined ? "—" : money(position.currentValue, baseCurrency)}</td>
                    <td>{position.asset?.latest_quote?.source ?? "—"}</td>
                    <td className={position.pnl === undefined ? "" : position.pnl >= 0 ? "positive" : "negative"}>
                      {position.pnl === undefined ? "—" : `${position.pnl >= 0 ? "+" : ""}${money(position.pnl, baseCurrency)}`}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={5}>
                      <p className="missing-value">{portfolio ? "В портфеле пока нет оценённых позиций." : "Портфели ещё не созданы."}</p>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </article>
        {eventPanel}
      </section>
    </>
  );
}
