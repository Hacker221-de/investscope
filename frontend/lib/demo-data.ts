import type { Asset, PoliticalEvent } from "./types";

export const assets: Asset[] = [
  { symbol: "AAPL", name: "Apple Inc.", type: "Equity", sector: "Technology", price: 213.49, change: 1.24, fairValue: 221, rating: "HOLD" },
  { symbol: "MSFT", name: "Microsoft Corporation", type: "Equity", sector: "Technology", price: 458.17, change: 0.62, fairValue: 472, rating: "BUY" },
  { symbol: "NVDA", name: "NVIDIA Corporation", type: "Equity", sector: "Semiconductors", price: 157.75, change: -0.84, fairValue: 165, rating: "HOLD" },
  { symbol: "TLT", name: "iShares 20+ Year Treasury Bond ETF", type: "ETF", sector: "Fixed Income", price: 88.92, change: 0.31, fairValue: 91.4, rating: "BUY" },
];

export const events: PoliticalEvent[] = [
  { date: "2026-07-01", time: "14:00 UTC", title: "Выступление руководителя центрального банка", region: "США", impact: "High", assets: ["TLT", "AAPL", "MSFT"], summary: "Сценарий для оценки влияния процентной политики на облигации и акции роста." },
  { date: "2026-07-08", time: "10:30 UTC", title: "Пересмотр правил экспорта технологий", region: "Мировой рынок", impact: "Medium", assets: ["NVDA"], summary: "Сценарий регуляторного риска для производителей полупроводников." },
  { date: "2026-07-16", time: "09:00 UTC", title: "Публикация обновлённого бюджетного плана", region: "Европа", impact: "Low", assets: ["TLT"], summary: "Сценарий для оценки реакции долгового рынка на бюджетную политику." },
];

export const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  currencyDisplay: "code",
  minimumFractionDigits: 2,
});
