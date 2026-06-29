import Link from "next/link";
import { notFound } from "next/navigation";

import { MetricCard, RatingBadge } from "@/components/ui";
import { assets, currency, pricePath } from "@/lib/demo-data";

export function generateStaticParams() {
  return assets.map((asset) => ({ symbol: asset.symbol }));
}

export default async function AssetDetailsPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = assets.find((item) => item.symbol === symbol.toUpperCase());
  if (!asset) notFound();

  const upside = ((asset.fairValue / asset.price - 1) * 100).toFixed(1);
  return (
    <>
      <Link href="/assets" className="back-link">← Back to assets</Link>
      <header className="asset-header">
        <div className="ticker-icon large">{asset.symbol.slice(0, 1)}</div>
        <div><p className="eyebrow">{asset.type} · {asset.sector}</p><h1>{asset.symbol} <span>{asset.name}</span></h1><p>Demo quote · Updated 12:00 UTC</p></div>
        <div className="asset-quote"><strong>{currency.format(asset.price)}</strong><span className={asset.change >= 0 ? "positive" : "negative"}>{asset.change >= 0 ? "+" : ""}{asset.change.toFixed(2)}%</span></div>
      </header>
      <section className="metrics-grid asset-metrics"><MetricCard label="Fair value" value={currency.format(asset.fairValue)} detail={`${upside}% model upside`} tone={Number(upside) > 0 ? "positive" : "negative"}/><MetricCard label="Market cap" value="$3.18T" detail="Demo fundamental"/><MetricCard label="P/E ratio" value="33.18×" detail="Forward estimate"/><MetricCard label="Dividend yield" value="0.45%" detail="Illustrative"/></section>
      <section className="dashboard-grid">
        <article className="panel chart-panel"><div className="panel-heading"><div><p className="eyebrow">Price history</p><h2>12-month performance</h2></div><div className="period-tabs"><button>1M</button><button>3M</button><button className="selected">1Y</button></div></div><svg className="main-chart asset-chart" viewBox="0 0 620 180" preserveAspectRatio="none"><path d={`${pricePath} L620 180 L0 180 Z`} fill="rgba(45,212,168,.10)"/><path d={pricePath} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke"/></svg><div className="chart-axis"><span>Jul 2025</span><span>Oct 2025</span><span>Jan 2026</span><span>Jun 2026</span></div></article>
        <article className="panel research-score"><div className="panel-heading"><div><p className="eyebrow">Composite research</p><h2>InvestScope score</h2></div><RatingBadge rating={asset.rating}/></div><div className="score-ring"><span><strong>78</strong><small>/ 100</small></span></div><ul className="score-list"><li>Fundamental quality <strong>86</strong></li><li>Valuation <strong>68</strong></li><li>Technical signal <strong>75</strong></li><li>Political risk <strong>Low</strong></li></ul></article>
      </section>
      <section className="analysis-grid"><article className="panel"><p className="eyebrow">Fundamental analysis</p><h2>Durable cash generation</h2><p>Illustrative analysis highlights margin stability and recurring revenue. Figures are synthetic and not sourced from filings.</p></article><article className="panel"><p className="eyebrow">Valuation</p><h2>Limited margin of safety</h2><p>The demo DCF implies {currency.format(asset.fairValue)} fair value under fixed assumptions. Sensitivity analysis is not yet implemented.</p></article><article className="panel"><p className="eyebrow">Risk note</p><h2>Concentration and policy</h2><p>Monitor sector concentration, rates, export policy and model uncertainty before changing the recorded portfolio allocation.</p></article></section>
    </>
  );
}
