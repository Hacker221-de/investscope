import type { ReactNode } from "react";

export function PageHeader({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">InvestScope / research workspace</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}

export function AnalyticsBanner() {
  return (
    <div className="demo-banner" role="note">
      <span>АНАЛИТИКА</span>
      <p>InvestScope анализирует введённые пользователем позиции, но не подключается к брокеру и не совершает сделки.</p>
    </div>
  );
}

export function MetricCard({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "positive" | "negative" | "neutral" }) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <small className={tone}>{detail}</small>
    </article>
  );
}

export function RatingBadge({ rating }: { rating: "BUY" | "HOLD" | "SELL" }) {
  return <span className={`badge rating-${rating.toLowerCase()}`}>{rating}</span>;
}

export function Sparkline({ negative = false }: { negative?: boolean }) {
  const points = negative ? "0,5 18,2 38,8 58,6 78,15 98,12" : "0,15 18,12 38,13 58,5 78,8 98,2";
  return (
    <svg className={negative ? "sparkline negative" : "sparkline"} viewBox="0 0 100 20" role="img" aria-label="Demo trend">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
