import { PortfolioManager } from "@/components/portfolio-manager";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Анализ портфеля" };

export default function PortfolioPage() {
  return (
    <>
      <PageHeader title="Анализ портфеля" description="Аналитика активов, которыми пользователь фактически владеет и указывает вручную." action={<span className="timestamp">Котировки: сохранённые рыночные данные</span>} />
      <div className="portfolio-disclaimer" role="note">InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки.</div>

      <PortfolioManager />

      <section className="portfolio-analytics-grid single-analytics">
        <article className="panel risk-list-panel"><p className="eyebrow">Экспозиция</p><h2>Политические и географические риски</h2><ul><li><span>US</span>Концентрация эмитентов в юрисдикции США</li><li><span>TECH</span>Экспортное регулирование технологического сектора</li><li><span>RATE</span>Процентный риск долговых инструментов</li></ul></article>
      </section>

      <section className="panel news-impact-panel"><div className="panel-heading"><div><p className="eyebrow">Информационные факторы</p><h2>Влияние последних новостей на активы портфеля</h2></div><span className="timestamp">Обновлено 09:30 UTC</span></div><div className="news-impact-list"><article><span className="impact negative-news">Негативное</span><div><strong>Пересмотр регулирования технологического сектора</strong><p>Политическая неопределённость повышает риск-премию позиций AAPL и MSFT.</p></div><div className="asset-pills"><span>AAPL</span><span>MSFT</span></div></article><article><span className="impact positive-news">Позитивное</span><div><strong>Стабилизация долгосрочных доходностей</strong><p>Стабилизация доходностей поддерживает оценку позиции TLT.</p></div><div className="asset-pills"><span>TLT</span></div></article></div></section>
    </>
  );
}
