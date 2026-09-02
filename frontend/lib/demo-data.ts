import type { PoliticalEvent } from "./types";

export const events: PoliticalEvent[] = [
  { date: "2026-07-01", time: "14:00 UTC", title: "Выступление руководителя центрального банка", region: "США", impact: "High", assets: ["TLT", "AAPL", "MSFT"], summary: "Сценарий для оценки влияния процентной политики на облигации и акции роста." },
  { date: "2026-07-08", time: "10:30 UTC", title: "Пересмотр правил экспорта технологий", region: "Мировой рынок", impact: "Medium", assets: ["NVDA"], summary: "Сценарий регуляторного риска для производителей полупроводников." },
  { date: "2026-07-16", time: "09:00 UTC", title: "Публикация обновлённого бюджетного плана", region: "Европа", impact: "Low", assets: ["TLT"], summary: "Сценарий для оценки реакции долгового рынка на бюджетную политику." },
];
