import Link from "next/link";

import { PageHeader, RatingBadge } from "@/components/ui";
import { assets, currency } from "@/lib/demo-data";

export const metadata = { title: "Аналитические рейтинги" };

const ratingDetails: Record<string, { rationale: string; confidence: number }> = {
  MSFT: { rationale: "Устойчивые денежные потоки и рост облачного направления компенсируют повышенную стоимостную оценку.", confidence: 86 },
  AAPL: { rationale: "Рост сервисной выручки поддерживает бизнес, однако текущая цена оставляет ограниченный запас прочности.", confidence: 74 },
  TLT: { rationale: "Стабилизация инфляции может поддержать длинные облигации, при этом сохраняется высокий процентный риск.", confidence: 71 },
};

const sectorLabel: Record<string, string> = {
  Technology: "Технологии",
  "Fixed Income": "Облигации",
  Semiconductors: "Полупроводники",
};

export default function RecommendationsPage() {
  const ratings = [assets[1], assets[0], assets[3]];
  return (
    <>
      <PageHeader title="Аналитические рейтинги" description="Объяснимые оценки на основе фундаментальных, стоимостных, технических и политических факторов." action={<span className="timestamp">Расчёт от 29.06.2026 · 08:00 UTC</span>} />
      <section className="research-summary"><div><strong>3</strong><span>Активных рейтинга</span></div><div><strong>2</strong><span>Положительных</span></div><div><strong>1</strong><span>Нейтральный</span></div><div><strong>12 мес.</strong><span>Горизонт оценки</span></div></section>
      <section className="recommendation-list">
        {ratings.map((asset, index) => {
          const potential = (asset.fairValue / asset.price - 1) * 100;
          const details = ratingDetails[asset.symbol];
          return (
            <article className="panel recommendation-card" key={asset.symbol}>
              <div className="recommendation-rank">0{index + 1}</div>
              <div className="recommendation-main"><div className="panel-heading"><div><Link href={`/assets/${asset.symbol}`}><h2>{asset.symbol} <span>{asset.name}</span></h2></Link><p>{sectorLabel[asset.sector] ?? asset.sector} · Горизонт: 12 месяцев</p></div><RatingBadge rating={asset.rating}/></div><p className="rationale">{details.rationale}</p><div className="factor-bars"><div><span>Фундаментальная оценка</span><i><b style={{ width: `${86 - index * 6}%` }}/></i><strong>{86 - index * 6}</strong></div><div><span>Стоимостная оценка</span><i><b style={{ width: `${68 + index * 3}%` }}/></i><strong>{68 + index * 3}</strong></div><div><span>Технический анализ</span><i><b style={{ width: `${75 - index * 5}%` }}/></i><strong>{75 - index * 5}</strong></div></div><div className="rating-metadata"><span>Дата расчёта: <strong>29.06.2026</strong></span><span>Версия модели: <strong>IS-RANK 1.0</strong></span><span>Уверенность: <strong>{details.confidence}%</strong></span></div></div>
              <aside className="recommendation-price"><small>Текущая цена</small><strong>{currency.format(asset.price)}</strong><small>Расчётная стоимость</small><strong>{currency.format(asset.fairValue)}</strong><span className={potential >= 0 ? "positive" : "negative"}>Расчётный потенциал: {potential >= 0 ? "+" : ""}{potential.toFixed(1)}%</span></aside>
            </article>
          );
        })}
      </section>
      <div className="method-note"><strong>Методика</strong><p>Рейтинги объединяют результаты аналитических модулей на демонстрационных данных. Это не индивидуальная инвестиционная рекомендация.</p></div>
    </>
  );
}
