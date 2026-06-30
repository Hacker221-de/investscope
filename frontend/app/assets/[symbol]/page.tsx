import Link from "next/link";
import { notFound } from "next/navigation";

import { AssetMarketData } from "@/components/asset-market-data";
import { MetricCard, RatingBadge } from "@/components/ui";
import { assets, currency } from "@/lib/demo-data";

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
      <section className="metrics-grid asset-metrics"><MetricCard label="Расчётная стоимость" value={currency.format(asset.fairValue)} detail="Демонстрационная аналитическая модель"/><MetricCard label="Рыночная капитализация" value="USD 3.18 трлн" detail="Демонстрационный показатель"/><MetricCard label="Коэффициент P/E" value="33.18×" detail="Демонстрационный показатель"/><MetricCard label="Дивидендная доходность" value="0.45%" detail="Демонстрационный показатель"/></section>
      <section className="dashboard-grid">
        <article className="panel research-score"><div className="panel-heading"><div><p className="eyebrow">Сводная оценка</p><h2>Рейтинг InvestScope</h2></div><RatingBadge rating={asset.rating}/></div><div className="score-ring"><span><strong>78</strong><small>из 100</small></span></div><ul className="score-list"><li>Фундаментальная оценка <strong>86</strong></li><li>Стоимостная оценка <strong>68</strong></li><li>Технический анализ <strong>75</strong></li><li>Политический риск <strong>Низкий</strong></li></ul></article>
      </section>
      <section className="analysis-grid"><article className="panel"><p className="eyebrow">Фундаментальная оценка</p><h2>Устойчивое формирование денежных потоков</h2><p>Демонстрационная оценка учитывает стабильность маржи и долю регулярной выручки. Показатели не получены из официальной отчётности.</p></article><article className="panel"><p className="eyebrow">Стоимостная оценка</p><h2>Ограниченный запас прочности</h2><p>Расчётная модель даёт стоимость {currency.format(asset.fairValue)} при фиксированных допущениях. Анализ чувствительности пока не реализован.</p></article><article className="panel"><p className="eyebrow">Факторы риска</p><h2>Концентрация и регулирование</h2><p>При анализе позиции учитываются сектор, процентные ставки, экспортная политика и неопределённость модели.</p></article></section>
    </>
  );
}
