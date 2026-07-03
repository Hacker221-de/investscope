import Link from "next/link";
import { notFound } from "next/navigation";

import { AssetMarketData } from "@/components/asset-market-data";
import { FundamentalAnalysis } from "@/components/fundamental-analysis";
import { CompanyProfileCard } from "@/components/fundamentals/company-profile-card";
import { SecFilingsTable } from "@/components/fundamentals/sec-filings-table";
import { RatingBadge } from "@/components/ui";
import { assets } from "@/lib/demo-data";

export function generateStaticParams() {
  return assets.map((asset) => ({ symbol: asset.symbol }));
}

export default async function AssetDetailsPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const asset = assets.find((item) => item.symbol === symbol.toUpperCase());
  if (!asset) notFound();

  return (
    <>
      <Link href="/assets" className="back-link">← Вернуться к активам</Link>
      <AssetMarketData asset={asset} />
      <CompanyProfileCard symbol={asset.symbol} />
      <FundamentalAnalysis symbol={asset.symbol} />
      <SecFilingsTable symbol={asset.symbol} />
      <section className="dashboard-grid asset-demo-rating">
        <article className="panel research-score">
          <div className="panel-heading">
            <div><p className="eyebrow">Демонстрационная модель</p><h2>Рейтинг InvestScope <span className="demo-model-badge">Демо</span></h2></div>
            <RatingBadge rating={asset.rating} />
          </div>
          <p className="demo-rating-note">Этот рейтинг использует демонстрационные данные и визуально отделён от официальных SEC-данных выше.</p>
          <div className="score-ring"><span><strong>78</strong><small>из 100</small></span></div>
          <ul className="score-list">
            <li>Фундаментальная оценка <strong>86</strong></li>
            <li>Стоимостная оценка <strong>68</strong></li>
            <li>Технический анализ <strong>75</strong></li>
            <li>Политический риск <strong>Низкий</strong></li>
          </ul>
        </article>
      </section>
    </>
  );
}
