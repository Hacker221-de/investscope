import Link from "next/link";

import { MetricCard, PageHeader, RatingBadge, Sparkline } from "@/components/ui";
import { assets, currency, events, positions, pricePath } from "@/lib/demo-data";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Portfolio pulse, research signals and upcoming risk events."
        action={<span className="timestamp">Updated 12:00 UTC</span>}
      />

      <section className="metrics-grid" aria-label="Portfolio metrics">
        <MetricCard label="Portfolio value" value="$87,879.58" detail="Owned positions" />
        <MetricCard label="Invested capital" value="$80,200.00" detail="Including entered fees" />
        <MetricCard label="Unrealized P&L" value="+$7,679.58" detail="+9.58% total return" tone="positive" />
        <MetricCard label="Research signals" value="3 active" detail="2 buy · 1 hold" />
      </section>

      <section className="dashboard-grid">
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Owned positions</p><h2>Portfolio performance</h2></div>
            <div className="period-tabs"><button>1M</button><button className="selected">3M</button><button>1Y</button></div>
          </div>
          <div className="chart-value"><strong>+8.42%</strong><span>vs S&P 500 +5.16%</span></div>
          <svg className="main-chart" viewBox="0 0 620 180" preserveAspectRatio="none" role="img" aria-label="Synthetic three month performance chart">
            <defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#2dd4a8" stopOpacity=".22"/><stop offset="100%" stopColor="#2dd4a8" stopOpacity="0"/></linearGradient></defs>
            <path d={`${pricePath} L620 180 L0 180 Z`} fill="url(#chartFill)" />
            <path d={pricePath} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="chart-axis"><span>Apr 01</span><span>May 01</span><span>Jun 01</span><span>Jun 29</span></div>
        </article>

        <article className="panel allocation-panel">
          <div className="panel-heading"><div><p className="eyebrow">Exposure</p><h2>Allocation</h2></div></div>
          <div className="donut" aria-label="Portfolio allocation"><span><strong>41.7%</strong><small>largest position</small></span></div>
          <ul className="legend"><li><i className="teal"/>Technology <strong>70.9%</strong></li><li><i className="blue"/>Fixed income <strong>29.1%</strong></li></ul>
        </article>
      </section>

      <section className="dashboard-grid lower-grid">
        <article className="panel wide-panel">
          <div className="panel-heading"><div><p className="eyebrow">Holdings</p><h2>Top positions</h2></div><Link href="/portfolio">View portfolio →</Link></div>
          <div className="table-wrap"><table><thead><tr><th>Asset</th><th>Price</th><th>Market value</th><th>Daily trend</th><th>P&L</th></tr></thead><tbody>
            {positions.map((position) => <tr key={position.symbol}><td><Link className="asset-symbol" href={`/assets/${position.symbol}`}><strong>{position.symbol}</strong><small>{assets.find((item) => item.symbol === position.symbol)?.name}</small></Link></td><td>{currency.format(position.currentPrice)}</td><td>{currency.format(position.currentValue)}</td><td><Sparkline negative={position.symbol === "TLT"}/></td><td className={position.pnl >= 0 ? "positive" : "negative"}>{position.pnl >= 0 ? "+" : ""}{currency.format(position.pnl)}</td></tr>)}
          </tbody></table></div>
        </article>

        <article className="panel event-panel">
          <div className="panel-heading"><div><p className="eyebrow">Risk calendar</p><h2>Upcoming events</h2></div><Link href="/political-events">All →</Link></div>
          {events.slice(0, 2).map((event) => <div className="event-row" key={event.title}><div className="event-date"><strong>{event.date.slice(-2)}</strong><small>JUL</small></div><div><span className={`impact ${event.impact.toLowerCase()}`}>{event.impact}</span><h3>{event.title}</h3><p>{event.time} · {event.region}</p></div></div>)}
        </article>
      </section>

      <section className="panel recommendations-strip">
        <div><p className="eyebrow">Latest research</p><h2>Recommendation watch</h2></div>
        {assets.slice(0, 3).map((asset) => <Link href={`/assets/${asset.symbol}`} className="mini-recommendation" key={asset.symbol}><span><strong>{asset.symbol}</strong><small>Fair value {currency.format(asset.fairValue)}</small></span><RatingBadge rating={asset.rating} /></Link>)}
        <Link href="/recommendations" className="text-link">Open research →</Link>
      </section>
    </>
  );
}
