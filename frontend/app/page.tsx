import Link from "next/link";

import { DashboardPortfolioSummary } from "@/components/dashboard-portfolio-summary";
import { PageHeader, RatingBadge } from "@/components/ui";
import { assets, currency, events } from "@/lib/demo-data";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Обзор"
        description="Сводка по портфелю, аналитическим рейтингам и ближайшим факторам риска."
        action={<span className="timestamp">Обновлено в 12:00 UTC</span>}
      />

      <DashboardPortfolioSummary eventPanel={
        <article className="panel event-panel">
          <div className="panel-heading"><div><p className="eyebrow">Календарь рисков</p><h2>Ближайшие события</h2></div><Link href="/political-events">Все →</Link></div>
          {events.slice(0, 2).map((event) => <div className="event-row" key={event.title}><div className="event-date"><strong>{event.date.slice(-2)}</strong><small>ИЮЛ</small></div><div><span className={`impact ${event.impact.toLowerCase()}`}>{event.impact === "High" ? "Высокое" : "Среднее"}</span><h3>{event.title}</h3><p>{event.time} · {event.region}</p></div></div>)}
        </article>
      } />

      <section className="panel recommendations-strip">
        <div><p className="eyebrow">Последний расчёт</p><h2>Аналитические рейтинги</h2></div>
        {assets.slice(0, 3).map((asset) => <Link href={`/assets/${asset.symbol}`} className="mini-recommendation" key={asset.symbol}><span><strong>{asset.symbol}</strong><small>Расчётная стоимость {currency.format(asset.fairValue)}</small></span><RatingBadge rating={asset.rating} /></Link>)}
        <Link href="/recommendations" className="text-link">Все рейтинги →</Link>
      </section>
    </>
  );
}
