import { formatDateTimeUtc, formatProvider } from "@/lib/fundamental-formatters";
import type { FundamentalCompleteness, FundamentalMarketPrice } from "@/lib/types";

function completenessText(status: string): string {
  if (status === "complete") return "Полные данные";
  if (status === "partial") return "Частичные данные";
  if (status === "insufficient_data") return "Недостаточно данных";
  return status;
}

function percentage(value: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return `${(Math.abs(parsed) <= 1 ? parsed * 100 : parsed).toFixed(0)}%`;
}

function metricName(metric: string): string {
  return metric.replaceAll("_", " ");
}

export function FundamentalQuality({
  completeness,
  warnings,
  marketPrice,
}: {
  completeness: FundamentalCompleteness;
  warnings: string[];
  marketPrice: FundamentalMarketPrice | null;
}) {
  return (
    <section className="panel fundamental-quality" aria-labelledby="fundamental-quality-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Качество данных</p>
          <h3 id="fundamental-quality-title">{completenessText(completeness.status)}</h3>
        </div>
        <strong className="completeness-ratio">{percentage(completeness.ratio)}</strong>
      </div>
      <div className="fundamental-quality-grid">
        <div><span>Доступно метрик</span><strong>{completeness.available_metrics}</strong></div>
        <div><span>Ожидается метрик</span><strong>{completeness.expected_metrics}</strong></div>
        <div><span>Рыночная цена</span><strong>{marketPrice ? formatProvider(marketPrice.provider) : "Нет данных"}</strong>{marketPrice && <small>{formatDateTimeUtc(marketPrice.received_at)}</small>}</div>
        <div><span>Актуальность цены</span><strong>{marketPrice ? (marketPrice.is_stale ? "Устарела" : "Актуальна") : "Не применимо"}</strong></div>
      </div>
      {marketPrice?.is_stale && <span className="quality-badge warning">Рыночная цена устарела</span>}
      {warnings.length > 0 && <div className="fundamental-warnings">{warnings.map((warning) => <span key={warning}>{warning}</span>)}</div>}
      {completeness.missing_metrics.length > 0 && (
        <details className="missing-metrics">
          <summary>Отсутствующие метрики ({completeness.missing_metrics.length})</summary>
          <p>{completeness.missing_metrics.map(metricName).join(", ")}</p>
        </details>
      )}
    </section>
  );
}
