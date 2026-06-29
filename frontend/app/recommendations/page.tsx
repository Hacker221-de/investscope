import Link from "next/link";

import { PageHeader, RatingBadge } from "@/components/ui";
import { assets, currency } from "@/lib/demo-data";

export const metadata = { title: "Recommendations" };

const rationale: Record<string, string> = {
  MSFT: "Strong cash generation and resilient cloud growth; valuation remains elevated.",
  AAPL: "Stable services mix offsets a limited near-term margin of safety.",
  TLT: "Duration exposure may benefit from easing inflation, with meaningful rate risk.",
};

export default function RecommendationsPage() {
  const recommendations = [assets[1], assets[0], assets[3]];
  return (
    <>
      <PageHeader title="Recommendations" description="Explainable research ratings across fundamental, valuation, technical and policy factors." action={<span className="timestamp">Generated 08:00 UTC</span>} />
      <section className="research-summary"><div><strong>3</strong><span>Active ratings</span></div><div><strong>2</strong><span>Buy</span></div><div><strong>1</strong><span>Hold</span></div><div><strong>12 mo</strong><span>Default horizon</span></div></section>
      <section className="recommendation-list">
        {recommendations.map((asset, index) => (
          <article className="panel recommendation-card" key={asset.symbol}>
            <div className="recommendation-rank">0{index + 1}</div>
            <div className="recommendation-main"><div className="panel-heading"><div><Link href={`/assets/${asset.symbol}`}><h2>{asset.symbol} <span>{asset.name}</span></h2></Link><p>{asset.sector} · 12-month horizon</p></div><RatingBadge rating={asset.rating}/></div><p className="rationale">{rationale[asset.symbol]}</p><div className="factor-bars"><div><span>Fundamentals</span><i><b style={{ width: `${86 - index * 6}%` }}/></i><strong>{86 - index * 6}</strong></div><div><span>Valuation</span><i><b style={{ width: `${68 + index * 3}%` }}/></i><strong>{68 + index * 3}</strong></div><div><span>Technicals</span><i><b style={{ width: `${75 - index * 5}%` }}/></i><strong>{75 - index * 5}</strong></div></div></div>
            <aside className="recommendation-price"><small>Demo price</small><strong>{currency.format(asset.price)}</strong><small>Fair value</small><strong>{currency.format(asset.fairValue)}</strong><span className="positive">+{((asset.fairValue / asset.price - 1) * 100).toFixed(1)}% implied</span></aside>
          </article>
        ))}
      </section>
      <div className="method-note"><strong>Rating method</strong><p>Scores combine deterministic demonstration outputs from the analysis modules. They have not been validated against live data and are not investment advice.</p></div>
    </>
  );
}

