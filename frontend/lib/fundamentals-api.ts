import { MarketApiError, fetchMarketApi } from "@/lib/api";
import type {
  FundamentalCompanyProfile,
  FundamentalFiling,
  FundamentalMetricsView,
  FundamentalPeriodType,
} from "@/lib/types";

export interface FundamentalFilingsOptions {
  form?: string;
  filedFrom?: string;
  filedTo?: string;
  asOf?: string;
  limit?: number;
  offset?: number;
}

export interface FundamentalMetricsOptions {
  periodType?: FundamentalPeriodType;
  asOf?: string;
  limit?: number;
  offset?: number;
  includeAlternatives?: boolean;
  annualFallback?: boolean;
}

function symbolPath(symbol: string): string {
  return encodeURIComponent(symbol.trim().toUpperCase());
}

function withQuery(path: string, values: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined) query.set(key, String(value));
  });
  const serialized = query.toString();
  return serialized ? `${path}?${serialized}` : path;
}

export function getFundamentalProfile(symbol: string): Promise<FundamentalCompanyProfile> {
  return fetchMarketApi<FundamentalCompanyProfile>(`/fundamentals/${symbolPath(symbol)}/profile`);
}

export function getFundamentalFilings(
  symbol: string,
  options: FundamentalFilingsOptions = {},
): Promise<FundamentalFiling[]> {
  return fetchMarketApi<FundamentalFiling[]>(withQuery(
    `/fundamentals/${symbolPath(symbol)}/filings`,
    {
      form: options.form,
      filed_from: options.filedFrom,
      filed_to: options.filedTo,
      as_of: options.asOf,
      limit: options.limit ?? 8,
      offset: options.offset,
    },
  ));
}

export function getFundamentalMetrics(
  symbol: string,
  options: FundamentalMetricsOptions = {},
): Promise<FundamentalMetricsView> {
  return fetchMarketApi<FundamentalMetricsView>(withQuery(
    `/fundamentals/${symbolPath(symbol)}/metrics`,
    {
      period_type: options.periodType ?? "quarterly",
      as_of: options.asOf,
      limit: options.limit,
      offset: options.offset,
      include_alternatives: options.includeAlternatives ?? false,
      annual_fallback: options.annualFallback,
    },
  ));
}

export function getFundamentalErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof MarketApiError) {
    if (typeof error.detail === "string" && error.detail.trim()) return error.detail;
    if (error.detail && typeof error.detail === "object") {
      const detail = error.detail as { message?: unknown; detail?: unknown; code?: unknown };
      if (typeof detail.message === "string" && detail.message.trim()) return detail.message;
      if (typeof detail.detail === "string" && detail.detail.trim()) return detail.detail;
      if (typeof detail.code === "string" && detail.code.trim()) return `${fallback} (${detail.code})`;
    }
    return `${fallback} (HTTP ${error.status})`;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}
