export type Trend = "up" | "down" | "flat";
export type Rating = "BUY" | "HOLD" | "SELL";

export interface Asset {
  symbol: string;
  name: string;
  type: "Equity" | "ETF";
  sector: string;
  price: number;
  change: number;
  fairValue: number;
  rating: Rating;
}

export interface Position {
  id: number;
  symbol: string;
  quantity: number;
  averagePurchasePrice: number;
  purchaseDate: string;
  currency: string;
  fees?: number;
  sector: string;
  geography: string;
  currentPrice: number;
  currentValue: number;
  pnl: number;
  weight: number;
}

export interface MarketQuote {
  close: string;
  previous_close: string | null;
  change: string | null;
  change_percent: string | null;
  currency: string;
  source: string;
  event_time: string;
  published_at: string | null;
  received_at: string;
  is_stale: boolean;
}

export interface MarketAsset {
  id: number;
  symbol: string;
  name: string;
  asset_type: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  currency: string;
  provider_symbol: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  latest_quote: MarketQuote | null;
}

export interface MarketBar {
  timeframe: string;
  event_time: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  adjusted_close: string | null;
  volume: number | null;
  provider: string;
  published_at: string | null;
  received_at: string;
}

export interface PoliticalEvent {
  date: string;
  time: string;
  title: string;
  region: string;
  impact: "High" | "Medium" | "Low";
  assets: string[];
  summary: string;
}
