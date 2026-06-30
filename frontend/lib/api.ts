const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const API_ROOT = process.env.NEXT_PUBLIC_API_ROOT ?? "http://localhost:8000";

export async function fetchFromApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`InvestScope API request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchMarketApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_ROOT}/api${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Market data request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}
