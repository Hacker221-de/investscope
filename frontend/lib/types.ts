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

export interface PoliticalEvent {
  date: string;
  time: string;
  title: string;
  region: string;
  impact: "High" | "Medium" | "Low";
  assets: string[];
  summary: string;
}
