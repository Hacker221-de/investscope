import Link from "next/link";

export default function AssetNotFound() {
  return <section className="empty-state"><span>404</span><h1>Asset not found</h1><p>The symbol is not part of the demonstration coverage universe.</p><Link href="/assets" className="primary-button">Return to assets</Link></section>;
}

