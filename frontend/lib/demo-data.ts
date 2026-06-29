import type { Asset, PoliticalEvent, Position } from "./types";

export const assets: Asset[] = [
  { symbol: "AAPL", name: "Apple Inc.", type: "Equity", sector: "Technology", price: 213.49, change: 1.24, fairValue: 221, rating: "HOLD" },
  { symbol: "MSFT", name: "Microsoft Corporation", type: "Equity", sector: "Technology", price: 458.17, change: 0.62, fairValue: 472, rating: "BUY" },
  { symbol: "NVDA", name: "NVIDIA Corporation", type: "Equity", sector: "Semiconductors", price: 157.75, change: -0.84, fairValue: 165, rating: "HOLD" },
  { symbol: "TLT", name: "iShares 20+ Year Treasury Bond ETF", type: "ETF", sector: "Fixed Income", price: 88.92, change: 0.31, fairValue: 91.4, rating: "BUY" },
];

export const positions: Position[] = [
  { id: 1, symbol: "AAPL", quantity: 120, averagePurchasePrice: 184.25, purchaseDate: "2024-03-14", currency: "USD", fees: 25, sector: "Technology", geography: "United States", currentPrice: 213.49, currentValue: 25618.8, pnl: 3483.8, weight: 29.15 },
  { id: 2, symbol: "MSFT", quantity: 80, averagePurchasePrice: 401.1, purchaseDate: "2024-09-05", currency: "USD", fees: 18, sector: "Technology", geography: "United States", currentPrice: 458.17, currentValue: 36653.6, pnl: 4547.6, weight: 41.71 },
  { id: 3, symbol: "TLT", quantity: 287.98, averagePurchasePrice: 90.1, purchaseDate: "2025-01-22", currency: "USD", fees: 12, sector: "Fixed Income", geography: "United States", currentPrice: 88.92, currentValue: 25607.18, pnl: -351.82, weight: 29.14 },
];

export const events: PoliticalEvent[] = [
  { date: "2026-07-01", time: "14:00 UTC", title: "Central bank policy testimony", region: "United States", impact: "High", assets: ["TLT", "AAPL", "MSFT"], summary: "Demo scenario for assessing rate-sensitive assets; not a live event feed." },
  { date: "2026-07-08", time: "10:30 UTC", title: "Technology export policy review", region: "Global", impact: "Medium", assets: ["NVDA"], summary: "Illustrative policy-risk event for semiconductor exposure." },
  { date: "2026-07-16", time: "09:00 UTC", title: "Regional fiscal policy update", region: "Europe", impact: "Low", assets: ["TLT"], summary: "Synthetic calendar entry used to demonstrate filtering and impact labels." },
];

export const pricePath = "M0 156 C45 150, 55 120, 94 129 S155 88, 190 101 S245 52, 286 73 S340 40, 390 51 S445 18, 500 30 S555 13, 620 20";

export const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
});
