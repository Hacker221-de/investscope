import { PageHeader } from "@/components/ui";
import { events } from "@/lib/demo-data";

export const metadata = { title: "Политические события" };

const impactLabel = { High: "Высокое", Medium: "Среднее", Low: "Низкое" } as const;

export default function PoliticalEventsPage() {
  return (
    <>
      <PageHeader title="Политические события" description="Календарь факторов, которые могут повлиять на отрасли, регионы и активы портфеля." action={<span className="timestamp">Часовой пояс: UTC</span>} />
      <section className="toolbar panel"><select defaultValue="all" aria-label="Регион"><option value="all">Все регионы</option><option>США</option><option>Мировой рынок</option><option>Европа</option></select><select defaultValue="all" aria-label="Уровень влияния"><option value="all">Любой уровень влияния</option><option>Высокое</option><option>Среднее</option><option>Низкое</option></select><select defaultValue="30" aria-label="Период"><option value="30">Следующие 30 дней</option><option value="90">Следующие 90 дней</option></select><span className="result-count">Демонстрационный календарь</span></section>
      <section className="events-layout"><div className="event-timeline">
        {events.map((event) => <article className="panel timeline-card" key={event.title}><div className="timeline-date"><strong>{event.date.slice(-2)}</strong><span>ИЮЛ</span><small>{event.time}</small></div><div className="timeline-body"><div><span className={`impact ${event.impact.toLowerCase()}`}>{impactLabel[event.impact]} влияние</span><span className="region-pill">{event.region}</span></div><h2>{event.title}</h2><p>{event.summary}</p><div className="asset-pills"><small>Затронутые активы</small>{event.assets.map((asset) => <span key={asset}>{asset}</span>)}</div></div><div className="risk-meter"><small>Оценка риска</small><strong>{event.impact === "High" ? "82" : event.impact === "Medium" ? "57" : "28"}</strong><span>из 100</span></div></article>)}
      </div><aside className="panel exposure-summary"><p className="eyebrow">Карта рисков портфеля</p><h2>Связь с позициями</h2><div className="exposure-score"><strong>64</strong><span>Средний</span></div><p>Позиции в технологиях и длинных облигациях связаны с двумя событиями календаря.</p><ul><li><span>Технологии</span><strong>70.9%</strong></li><li><span>Облигации</span><strong>29.1%</strong></li><li><span>События высокого влияния</span><strong>1</strong></li></ul><div className="method-note compact"><strong>Важно</strong><p>Это сценарная классификация рисков, а не политический прогноз или новостная лента.</p></div></aside></section>
    </>
  );
}
