import Link from "next/link";

import { MetricCard, PageHeader, RatingBadge, Sparkline } from "@/components/ui";
import { assets, currency, events, positions, pricePath } from "@/lib/demo-data";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="Обзор"
        description="Сводка по портфелю, аналитическим рейтингам и ближайшим факторам риска."
        action={<span className="timestamp">Обновлено в 12:00 UTC</span>}
      />

      <section className="metrics-grid" aria-label="Показатели портфеля">
        <MetricCard label="Текущая стоимость портфеля" value="USD 87,879.58" detail="По введённым позициям" />
        <MetricCard label="Вложенный капитал" value="USD 80,200.00" detail="С учётом комиссий" />
        <MetricCard label="Нереализованная прибыль / убыток" value="+USD 7,679.58" detail="Доходность: +9.58%" tone="positive" />
        <MetricCard label="Аналитические рейтинги" value="3 активных" detail="2 положительных · 1 нейтральный" />
      </section>

      <section className="dashboard-grid">
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Введённые позиции</p><h2>Динамика портфеля</h2></div>
            <div className="period-tabs"><button>1М</button><button className="selected">3М</button><button>1Г</button></div>
          </div>
          <div className="chart-value"><strong>+8.42%</strong><span>сравнительный индекс: +5.16%</span></div>
          <svg className="main-chart" viewBox="0 0 620 180" preserveAspectRatio="none" role="img" aria-label="Демонстрационная динамика портфеля за три месяца">
            <defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#2dd4a8" stopOpacity=".22"/><stop offset="100%" stopColor="#2dd4a8" stopOpacity="0"/></linearGradient></defs>
            <path d={`${pricePath} L620 180 L0 180 Z`} fill="url(#chartFill)" />
            <path d={pricePath} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke" />
          </svg>
          <div className="chart-axis"><span>1 апр.</span><span>1 мая</span><span>1 июня</span><span>29 июня</span></div>
        </article>

        <article className="panel allocation-panel">
          <div className="panel-heading"><div><p className="eyebrow">Распределение</p><h2>Структура портфеля</h2></div></div>
          <div className="donut" aria-label="Распределение портфеля"><span><strong>41.7%</strong><small>крупнейшая позиция</small></span></div>
          <ul className="legend"><li><i className="teal"/>Технологии <strong>70.9%</strong></li><li><i className="blue"/>Облигации <strong>29.1%</strong></li></ul>
        </article>
      </section>

      <section className="dashboard-grid lower-grid">
        <article className="panel wide-panel">
          <div className="panel-heading"><div><p className="eyebrow">Состав портфеля</p><h2>Крупнейшие позиции</h2></div><Link href="/portfolio">Открыть портфель →</Link></div>
          <div className="table-wrap"><table className="sticky-ticker"><thead><tr><th>Актив</th><th>Цена</th><th>Текущая стоимость</th><th>Динамика за день</th><th>Нереализованная прибыль / убыток</th></tr></thead><tbody>
            {positions.map((position) => <tr key={position.symbol}><td><Link className="asset-symbol" href={`/assets/${position.symbol}`}><strong>{position.symbol}</strong><small>{assets.find((item) => item.symbol === position.symbol)?.name}</small></Link></td><td>{currency.format(position.currentPrice)}</td><td>{currency.format(position.currentValue)}</td><td><Sparkline negative={position.symbol === "TLT"}/></td><td className={position.pnl >= 0 ? "positive" : "negative"}>{position.pnl >= 0 ? "+" : ""}{currency.format(position.pnl)}</td></tr>)}
          </tbody></table></div>
        </article>

        <article className="panel event-panel">
          <div className="panel-heading"><div><p className="eyebrow">Календарь рисков</p><h2>Ближайшие события</h2></div><Link href="/political-events">Все →</Link></div>
          {events.slice(0, 2).map((event) => <div className="event-row" key={event.title}><div className="event-date"><strong>{event.date.slice(-2)}</strong><small>ИЮЛ</small></div><div><span className={`impact ${event.impact.toLowerCase()}`}>{event.impact === "High" ? "Высокое" : "Среднее"}</span><h3>{event.title}</h3><p>{event.time} · {event.region}</p></div></div>)}
        </article>
      </section>

      <section className="panel recommendations-strip">
        <div><p className="eyebrow">Последний расчёт</p><h2>Аналитические рейтинги</h2></div>
        {assets.slice(0, 3).map((asset) => <Link href={`/assets/${asset.symbol}`} className="mini-recommendation" key={asset.symbol}><span><strong>{asset.symbol}</strong><small>Расчётная стоимость {currency.format(asset.fairValue)}</small></span><RatingBadge rating={asset.rating} /></Link>)}
        <Link href="/recommendations" className="text-link">Все рейтинги →</Link>
      </section>
    </>
  );
}
