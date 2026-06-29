import Link from "next/link";

import { PageHeader, RatingBadge, Sparkline } from "@/components/ui";
import { assets, currency } from "@/lib/demo-data";

export const metadata = { title: "Assets" };

export default function AssetsPage() {
  return (
    <>
      <PageHeader title="Assets" description="Explore the demonstration coverage universe and research signals." action={<button className="primary-button">+ Add to watchlist</button>} />
      <section className="toolbar panel"><label className="search-box"><span>⌕</span><input aria-label="Search assets" placeholder="Search by symbol or company" /></label><select aria-label="Asset type" defaultValue="all"><option value="all">All asset types</option><option>Equity</option><option>ETF</option></select><select aria-label="Sector" defaultValue="all"><option value="all">All sectors</option><option>Technology</option><option>Fixed Income</option></select><span className="result-count">4 demo assets</span></section>
      <section className="panel asset-table-panel">
        <div className="table-wrap"><table className="asset-table"><thead><tr><th>Asset</th><th>Type / sector</th><th>Price</th><th>24h change</th><th>Trend</th><th>Fair value</th><th>Rating</th></tr></thead><tbody>
          {assets.map((asset) => <tr key={asset.symbol}><td><Link className="asset-symbol" href={`/assets/${asset.symbol}`}><span className="ticker-icon">{asset.symbol.slice(0, 1)}</span><span><strong>{asset.symbol}</strong><small>{asset.name}</small></span></Link></td><td><strong>{asset.type}</strong><small className="cell-note">{asset.sector}</small></td><td><strong>{currency.format(asset.price)}</strong><small className="cell-note">USD</small></td><td className={asset.change >= 0 ? "positive" : "negative"}>{asset.change >= 0 ? "+" : ""}{asset.change.toFixed(2)}%</td><td><Sparkline negative={asset.change < 0}/></td><td>{currency.format(asset.fairValue)}</td><td><RatingBadge rating={asset.rating}/></td></tr>)}
        </tbody></table></div>
      </section>
      <p className="page-note">Coverage is limited to static demo records. Prices are not current and must not be used for investment decisions.</p>
    </>
  );
}

