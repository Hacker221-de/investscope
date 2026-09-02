import Link from "next/link";

import { DashboardRecommendationsStrip } from "@/components/dashboard-recommendations-strip";
import { DashboardPortfolioSummary } from "@/components/dashboard-portfolio-summary";
import { PageHeader } from "@/components/ui";
import { events } from "@/lib/demo-data";

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

      <DashboardRecommendationsStrip />
    </>
  );
}
