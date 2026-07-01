const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const API_ROOT = process.env.NEXT_PUBLIC_API_ROOT ?? "http://localhost:8000";

export async function fetchFromApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`InvestScope API request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export class MarketApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`Market data request failed with status ${status}`);
  }
}

export async function fetchMarketApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_ROOT}/api${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    throw new MarketApiError(response.status, payload?.detail);
  }
  return response.json() as Promise<T>;
}
