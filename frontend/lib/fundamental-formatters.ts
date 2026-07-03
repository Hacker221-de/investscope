import type { FundamentalMetricPoint } from "@/lib/types";

const compactNumber = new Intl.NumberFormat("ru-RU", {
  notation: "compact",
  maximumFractionDigits: 2,
});

function finiteNumber(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatExactDecimal(value: string | null, unit?: string | null): string {
  if (value === null) return "Нет данных";
  return unit ? `${value} ${unit}` : value;
}

export function formatDecimalString(value: string | null, maximumFractionDigits = 2): string {
  const parsed = finiteNumber(value);
  if (parsed === null) return value === null ? "Нет данных" : value;
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(parsed);
}

export function formatCompactDecimal(value: string | null): string {
  const parsed = finiteNumber(value);
  return parsed === null ? (value === null ? "Нет данных" : value) : compactNumber.format(parsed);
}

export function formatMoney(value: string | null, unit: string | null): string {
  const parsed = finiteNumber(value);
  if (parsed === null) return value === null ? "Нет данных" : formatExactDecimal(value, unit);
  if (!unit || !/^[A-Z]{3}$/.test(unit)) return `${compactNumber.format(parsed)} ${unit ?? "единица не указана"}`;
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: unit,
    currencyDisplay: "code",
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(parsed);
}

export function formatPercent(value: string | null): string {
  const parsed = finiteNumber(value);
  return parsed === null ? (value === null ? "Нет данных" : `${value}%`) : `${parsed.toFixed(1)}%`;
}

export function formatMetricValue(point: FundamentalMetricPoint | null): string {
  if (!point || point.status !== "available" || point.value === null) return "Нет данных";
  if (point.unit === "%") return formatPercent(point.value);
  if (point.unit === "ratio") return `${formatDecimalString(point.value, 2)}×`;
  if (point.unit && /^[A-Z]{3}$/.test(point.unit)) return formatMoney(point.value, point.unit);
  const value = formatCompactDecimal(point.value);
  return point.unit ? `${value} ${point.unit}` : `${value} · единица не указана`;
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeZone: "UTC" }).format(date);
}

export function formatDateTimeUtc(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return `${new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

export function formatFiscalPeriod(
  fiscalYear: number | null,
  fiscalPeriod: string | null,
  periodType?: string,
): string {
  if (periodType === "ttm") return "Последние 12 месяцев";
  if (fiscalYear === null && !fiscalPeriod) return "Финансовый период не указан";
  if (/^Q[1-4]$/.test(fiscalPeriod ?? "")) return `${fiscalPeriod} ${fiscalYear ?? "—"} фин. года`;
  return fiscalYear === null ? fiscalPeriod ?? "—" : `${fiscalYear} финансовый год`;
}

export function formatProvider(provider: string): string {
  return provider === "sec_edgar" ? "SEC EDGAR" : provider;
}

export function formatIngestionMethod(method: string): string {
  if (method === "manual_json") return "Официальные SEC JSON импортированы вручную";
  if (method === "api") return "Получено через API источника";
  return method;
}

const derivationLabels: Record<string, string> = {
  ratio: "Расчётное отношение",
  growth: "Расчёт темпа роста",
  annual_minus_three_quarters: "Годовое значение минус три квартала",
  ytd_difference: "Разница накопленных значений YTD",
  ttm_four_quarters: "Сумма четырёх кварталов TTM",
  market_valuation: "Рыночная оценка",
  non_overlapping_debt_components: "Сумма непересекающихся компонентов долга",
  free_cash_flow: "Расчёт свободного денежного потока",
  free_cash_flow_from_derived_quarters: "FCF из рассчитанных кварталов",
};

export function formatDerivationMethod(method: string | null): string {
  if (!method) return "Метод расчёта не указан";
  return derivationLabels[method] ?? method.replaceAll("_", " ");
}
