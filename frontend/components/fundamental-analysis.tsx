"use client";

import { useEffect, useMemo, useState } from "react";

import { CalculationComponents } from "@/components/fundamentals/calculation-components";
import { FundamentalQuality } from "@/components/fundamentals/fundamental-quality";
import { MetricProvenance } from "@/components/fundamentals/metric-provenance";
import { getFundamentalErrorMessage, getFundamentalMetrics } from "@/lib/fundamentals-api";
import {
  formatDate,
  formatFiscalPeriod,
  formatMetricValue,
} from "@/lib/fundamental-formatters";
import type { FundamentalMetricPoint, FundamentalMetricsView, FundamentalPeriodType } from "@/lib/types";

const labels: Record<string, string> = {
  revenue: "Выручка",
  gross_profit: "Валовая прибыль",
  operating_income: "Операционная прибыль",
  net_income: "Чистая прибыль",
  eps_basic: "Базовая прибыль на акцию",
  eps_diluted: "Разводнённая прибыль на акцию",
  operating_cash_flow: "Операционный денежный поток",
  capital_expenditures: "Капитальные затраты",
  free_cash_flow: "Свободный денежный поток",
  cash_and_equivalents: "Денежные средства",
  current_assets: "Оборотные активы",
  current_liabilities: "Краткосрочные обязательства",
  total_assets: "Активы",
  total_liabilities: "Обязательства",
  total_debt: "Общий долг",
  shareholders_equity: "Капитал акционеров",
  shares_outstanding: "Акции в обращении",
  revenue_growth_yoy: "Рост выручки год к году",
  net_income_growth_yoy: "Рост чистой прибыли год к году",
  gross_margin: "Валовая маржа",
  operating_margin: "Операционная маржа",
  net_margin: "Чистая маржа",
  free_cash_flow_margin: "Маржа свободного денежного потока",
  current_ratio: "Текущая ликвидность",
  debt_to_equity: "Долг / капитал",
  return_on_assets: "Рентабельность активов",
  return_on_equity: "Рентабельность капитала",
  shares_dilution_yoy: "Изменение числа акций год к году",
  market_cap: "Рыночная капитализация",
  price_to_earnings: "P/E",
  price_to_sales: "P/S",
  price_to_free_cash_flow: "P/FCF",
};

const warningText: Record<string, string> = {
  conflicting_facts: "Для периода найдены конфликтующие факты SEC",
  repeated_comparative: "Повторное сравнительное значение не использовано как новый период",
  restated_value: "Значение пересмотрено в более поздней отчётности",
  incomplete_ttm: "Недостаточно четырёх последовательных кварталов для TTM",
  missing_metric: "Часть показателей отсутствует",
  stale_market_price: "Рыночная цена устарела",
  zero_denominator: "Знаменатель равен нулю",
  invalid_denominator: "Знаменатель экономически некорректен",
  negative_net_income: "P/E не рассчитывается при отрицательной прибыли",
  missing_market_price: "Нет сохранённой рыночной цены",
  missing_shares: "Нет данных о числе акций",
  unit_mismatch: "Единицы исходных фактов не совпадают",
  annual_fallback: "Использовано годовое значение",
  derived_quarter_missing_source: "Недостаточно исходных SEC-фактов для расчёта квартала",
  derived_quarter_unit_mismatch: "Расчёт квартала невозможен: единицы исходных фактов различаются",
  derived_quarter_conflict: "Расчёт квартала невозможен из-за неоднозначных исходных фактов",
  derived_quarter_incompatible_concepts: "SEC concepts нельзя однозначно объединить в расчёте квартала",
  derived_quarter_incompatible_units: "Единицы EPS не допускают квартальную агрегацию",
  derived_quarter_invalid_periods: "Периоды исходных фактов не образуют корректный финансовый год",
  derived_quarter_missing_fiscal_year: "Не указан финансовый год исходного SEC-факта",
  mixed_concepts: "Расчёт использует совместимые альтернативные SEC concepts",
  eps_aggregation: "EPS рассчитан из сопоставимых периодов; возможен эффект округления",
};

function metricLabel(metric: string): string {
  return labels[metric] ?? metric.replaceAll("_", " ");
}

function latest(data: FundamentalMetricsView, metric: string): FundamentalMetricPoint | null {
  return data.metrics[metric]?.at(-1) ?? null;
}

function fiscalText(point: FundamentalMetricPoint): string {
  return formatFiscalPeriod(point.fiscal_year, point.fiscal_period, point.period_type);
}

function MetricBadges({ point }: { point: FundamentalMetricPoint }) {
  return (
    <span className="quality-badges">
      {point.derived && <span className="quality-badge derived">Расчётное значение</span>}
      {point.has_conflict && <span className="quality-badge conflict">Конфликт фактов</span>}
      {point.is_restated && <span className="quality-badge warning">Пересмотрено</span>}
      {point.is_repeated_comparative && <span className="quality-badge neutral">Comparative</span>}
      {point.status !== "available" && <span className="quality-badge unavailable">Нет данных</span>}
    </span>
  );
}

function linePoints(points: FundamentalMetricPoint[]): string {
  const values = points.flatMap((point) => {
    if (point.status !== "available" || point.value === null) return [];
    const value = Number(point.value);
    return Number.isFinite(value) ? [value] : [];
  });
  if (!values.length) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values.map((value, index) => {
    const x = values.length === 1 ? 300 : index / (values.length - 1) * 600;
    return `${x.toFixed(1)},${(130 - (value - min) / range * 110).toFixed(1)}`;
  }).join(" ");
}

function MetricChart({ title, points }: { title: string; points: FundamentalMetricPoint[] }) {
  const available = points.filter((point) => point.status === "available" && point.value !== null && Number.isFinite(Number(point.value)));
  const path = linePoints(available);
  return (
    <article className="panel fundamental-chart">
      <div className="panel-heading"><h3>{title}</h3><span className="timestamp">{available.length} периодов</span></div>
      {path ? <>
        <svg viewBox="0 0 600 145" preserveAspectRatio="none" role="img" aria-label={title}><polyline points={path} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke" /></svg>
        <div className="chart-axis"><span>{available[0]?.period_end}</span><span>{available.at(-1)?.period_end}</span></div>
      </> : <div className="fundamental-empty compact">Нет данных для графика</div>}
    </article>
  );
}

function MetricCards({ data, metrics }: { data: FundamentalMetricsView; metrics: string[] }) {
  return (
    <div className="metrics-grid fundamental-cards">
      {metrics.map((metric) => {
        const point = latest(data, metric);
        const numeric = point?.value === null || point?.value === undefined ? null : Number(point.value);
        return (
          <article className="metric-card" key={metric}>
            <p>{metricLabel(metric)}</p>
            <strong className={numeric === null || !Number.isFinite(numeric) ? "" : numeric >= 0 ? "positive" : "negative"}>{formatMetricValue(point)}</strong>
            {point && <MetricBadges point={point} />}
            <small>{point ? `${fiscalText(point)} · до ${formatDate(point.period_end)}` : "Показатель отсутствует"}</small>
            {point?.warnings.length ? <em className="metric-warning">{point.warnings.map((warning) => warningText[warning] ?? warning).join(" · ")}</em> : null}
          </article>
        );
      })}
    </div>
  );
}

function SummaryTable({ data, metrics, title }: { data: FundamentalMetricsView; metrics: string[]; title: string }) {
  return (
    <article className="panel wide-panel">
      <div className="panel-heading"><h3>{title}</h3></div>
      <div className="table-wrap"><table><tbody>{metrics.map((metric) => {
        const point = latest(data, metric);
        return <tr key={metric}><th>{metricLabel(metric)}</th><td>{formatMetricValue(point)}</td></tr>;
      })}</tbody></table></div>
    </article>
  );
}

function MetricsAudit({ data }: { data: FundamentalMetricsView }) {
  const points = Object.entries(data.metrics)
    .map(([metric, series]) => [metric, series.at(-1)] as const)
    .filter((entry): entry is readonly [string, FundamentalMetricPoint] => entry[1] !== undefined)
    .sort(([left], [right]) => metricLabel(left).localeCompare(metricLabel(right), "ru"));

  if (!points.length) return null;
  return (
    <section className="panel wide-panel fundamental-audit" aria-labelledby="metrics-audit-title">
      <div className="panel-heading">
        <div><p className="eyebrow">Provenance</p><h3 id="metrics-audit-title">Методика и аудит последних значений</h3></div>
        <span className="timestamp">{points.length} метрик</span>
      </div>
      <div className="fundamental-audit-list">{points.map(([metric, point]) => (
        <article className="fundamental-audit-card" key={metric}>
          <div className="audit-card-heading">
            <div><h4>{metricLabel(metric)}</h4><span>{fiscalText(point)} · {point.period_end}</span></div>
            <div><strong>{formatMetricValue(point)}</strong><MetricBadges point={point} /></div>
          </div>
          {point.confidence && <p className="audit-confidence">Уверенность: {point.confidence}</p>}
          {point.warnings.length > 0 && <p className="audit-warning">{point.warnings.map((warning) => warningText[warning] ?? warning).join(" · ")}</p>}
          <CalculationComponents point={point} />
          <MetricProvenance point={point} />
        </article>
      ))}</div>
    </section>
  );
}

export function FundamentalAnalysis({ symbol }: { symbol: string }) {
  const [periodType, setPeriodType] = useState<FundamentalPeriodType>("quarterly");
  const [data, setData] = useState<FundamentalMetricsView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getFundamentalMetrics(symbol, {
      periodType,
      limit: 12,
      includeAlternatives: true,
    })
      .then((response) => {
        if (active) setData(response);
      })
      .catch((reason: unknown) => {
        if (active) setError(getFundamentalErrorMessage(reason, "Не удалось загрузить фундаментальные метрики"));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [periodType, symbol]);

  const warnings = useMemo(() => data ? Array.from(new Set([
    ...data.warnings,
    ...Object.values(data.metrics).flat().flatMap((point) => point.warnings),
  ])).map((warning) => warningText[warning] ?? warning) : [], [data]);

  const balance = ["cash_and_equivalents", "current_assets", "current_liabilities", "total_assets", "total_liabilities", "total_debt", "shareholders_equity"];
  const margins = ["gross_margin", "operating_margin", "net_margin", "free_cash_flow_margin", "current_ratio", "debt_to_equity", "return_on_assets", "return_on_equity"];

  return (
    <section className="fundamental-section" aria-labelledby="fundamental-title">
      <div className="fundamental-heading">
        <div>
          <p className="eyebrow">SEC EDGAR / канонические ряды</p>
          <h2 id="fundamental-title">Фундаментальный анализ</h2>
          <p>Опубликованные SEC-факты и явно обозначенные расчётные метрики. Расчётные значения не выдаются за непосредственно опубликованные факты.</p>
        </div>
        <div className="segmented" aria-label="Тип периода">{(["quarterly", "annual", "ttm"] as FundamentalPeriodType[]).map((value) => (
          <button key={value} type="button" className={periodType === value ? "selected" : ""} onClick={() => setPeriodType(value)}>
            {value === "quarterly" ? "Квартальные" : value === "annual" ? "Годовые" : "TTM"}
          </button>
        ))}</div>
      </div>
      {loading && <div className="panel fundamental-state" role="status">Загрузка фундаментальных данных…</div>}
      {!loading && error && <div className="panel fundamental-state error" role="alert">{error}</div>}
      {!loading && !error && data && <FundamentalQuality completeness={data.completeness} warnings={warnings} marketPrice={data.market_price} />}
      {!loading && !error && data && data.periods.length === 0 && (
        <div className="panel fundamental-state"><strong>Недостаточно данных</strong><span>{periodType === "ttm" ? "TTM требует четырёх неперекрывающихся последовательных кварталов." : "Для выбранного периода нет канонических SEC-фактов."}</span></div>
      )}
      {!loading && !error && data && data.periods.length > 0 && <>
        <MetricCards data={data} metrics={["revenue", "net_income", "free_cash_flow", "total_debt"]} />
        <MetricCards data={data} metrics={["revenue_growth_yoy", "net_income_growth_yoy", "gross_margin", "net_margin"]} />
        <div className="fundamental-chart-grid">
          <MetricChart title="Динамика выручки" points={data.metrics.revenue ?? []} />
          <MetricChart title="Динамика чистой прибыли" points={data.metrics.net_income ?? []} />
          <MetricChart title="Свободный денежный поток" points={data.metrics.free_cash_flow ?? []} />
        </div>
        <div className="fundamental-table-grid">
          <SummaryTable data={data} metrics={balance} title="Баланс" />
          <SummaryTable data={data} metrics={margins} title="Маржинальность и эффективность" />
        </div>
        <MetricCards data={data} metrics={["shares_outstanding", "shares_dilution_yoy", "market_cap", "price_to_earnings", "price_to_sales", "price_to_free_cash_flow"]} />
        <MetricsAudit data={data} />
      </>}
    </section>
  );
}
