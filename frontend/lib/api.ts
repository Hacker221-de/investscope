import { buildLegacyApiUrl } from "@/lib/api-base";
import type {
  ApiErrorPayload,
  Portfolio,
  PortfolioCreate,
  PortfolioDetail,
  PortfolioUpdate,
  Position,
  PositionCreate,
  PositionUpdate,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_ROOT;
const API_ROOT = process.env.NEXT_PUBLIC_API_ROOT ?? process.env.NEXT_PUBLIC_API_URL;

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((item): item is string => Boolean(item));
    if (messages.length) return messages.join("; ");
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === "string" && record.message.trim()) return record.message;
    if (typeof record.code === "string" && record.code.trim()) return record.code;
  }
  return fallback;
}

async function readApiError(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null) as ApiErrorPayload | null;
  return payload?.detail ?? null;
}

function buildMarketApiUrl(path: string): string {
  const baseUrl = (API_ROOT ?? "").trim().replace(/\/+$/, "");
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  const apiPath = normalizedPath.startsWith("/api/")
    ? normalizedPath
    : `/api${normalizedPath}`;
  if (!baseUrl) return apiPath;
  if (baseUrl.endsWith("/api") && apiPath.startsWith("/api/")) {
    return `${baseUrl}${apiPath.slice("/api".length)}`;
  }
  return `${baseUrl}${apiPath}`;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(detailToMessage(detail, `InvestScope API request failed with status ${status}`));
    this.name = "ApiError";
  }
}

export async function fetchFromApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildLegacyApiUrl(API_URL, path), { cache: "no-store", ...init });
  if (!response.ok) {
    throw new ApiError(response.status, await readApiError(response));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export class MarketApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(detailToMessage(detail, `Market data request failed with status ${status}`));
    this.name = "MarketApiError";
  }
}

export async function fetchMarketApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildMarketApiUrl(path), { cache: "no-store", ...init });
  if (!response.ok) {
    throw new MarketApiError(response.status, await readApiError(response));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const jsonHeaders = { "Content-Type": "application/json" } as const;

export function formatApiError(error: unknown, fallback = "Не удалось выполнить запрос к InvestScope API."): string {
  if (error instanceof ApiError || error instanceof MarketApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function listPortfolios(): Promise<Portfolio[]> {
  return fetchFromApi<Portfolio[]>("/portfolios");
}

export function getPortfolio(portfolioId: number): Promise<PortfolioDetail> {
  return fetchFromApi<PortfolioDetail>(`/portfolios/${portfolioId}`);
}

export function createPortfolio(payload: PortfolioCreate): Promise<Portfolio> {
  return fetchFromApi<Portfolio>("/portfolios", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
}

export function updatePortfolio(
  portfolioId: number,
  payload: PortfolioUpdate,
): Promise<Portfolio> {
  return fetchFromApi<Portfolio>(`/portfolios/${portfolioId}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
}

export function deletePortfolio(portfolioId: number): Promise<void> {
  return fetchFromApi<void>(`/portfolios/${portfolioId}`, { method: "DELETE" });
}

export function listPositions(portfolioId: number): Promise<Position[]> {
  return fetchFromApi<Position[]>(`/portfolios/${portfolioId}/positions`);
}

export function createPosition(
  portfolioId: number,
  payload: PositionCreate,
): Promise<Position> {
  return fetchFromApi<Position>(`/portfolios/${portfolioId}/positions`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
}

export function updatePosition(
  portfolioId: number,
  positionId: number,
  payload: PositionUpdate,
): Promise<Position> {
  return fetchFromApi<Position>(`/portfolios/${portfolioId}/positions/${positionId}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
}

export function deletePosition(portfolioId: number, positionId: number): Promise<void> {
  return fetchFromApi<void>(`/portfolios/${portfolioId}/positions/${positionId}`, {
    method: "DELETE",
  });
}
