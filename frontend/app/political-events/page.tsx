import { PageHeader } from "@/components/ui";
import { events } from "@/lib/demo-data";

export const metadata = { title: "Political events" };

export default function PoliticalEventsPage() {
  return (
    <>
      <PageHeader title="Political events" description="Explore illustrative policy events and map potential portfolio exposure." action={<span className="timestamp">Calendar timezone: UTC</span>} />
      <section className="toolbar panel"><select defaultValue="all" aria-label="Region"><option value="all">All regions</option><option>United States</option><option>Global</option><option>Europe</option></select><select defaultValue="all" aria-label="Impact"><option value="all">All impact levels</option><option>High</option><option>Medium</option><option>Low</option></select><select defaultValue="30" aria-label="Date range"><option value="30">Next 30 days</option><option value="90">Next 90 days</option></select><span className="result-count">Synthetic calendar</span></section>
      <section className="events-layout"><div className="event-timeline">
        {events.map((event) => <article className="panel timeline-card" key={event.title}><div className="timeline-date"><strong>{event.date.slice(-2)}</strong><span>JUL</span><small>{event.time}</small></div><div className="timeline-body"><div><span className={`impact ${event.impact.toLowerCase()}`}>{event.impact} impact</span><span className="region-pill">{event.region}</span></div><h2>{event.title}</h2><p>{event.summary}</p><div className="asset-pills"><small>Affected demo assets</small>{event.assets.map((asset) => <span key={asset}>{asset}</span>)}</div></div><div className="risk-meter"><small>Risk score</small><strong>{event.impact === "High" ? "82" : event.impact === "Medium" ? "57" : "28"}</strong><span>/ 100</span></div></article>)}
      </div><aside className="panel exposure-summary"><p className="eyebrow">Portfolio map</p><h2>Event exposure</h2><div className="exposure-score"><strong>64</strong><span>Moderate</span></div><p>Technology and duration positions intersect with two demonstration events.</p><ul><li><span>Technology</span><strong>55.4%</strong></li><li><span>Fixed income</span><strong>22.8%</strong></li><li><span>High-impact events</span><strong>1</strong></li></ul><div className="method-note compact"><strong>Important</strong><p>This is scenario tagging, not political prediction or a live event service.</p></div></aside></section>
    </>
  );
}

