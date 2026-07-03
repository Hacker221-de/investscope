"use client";

import { FormEvent, useMemo, useState } from "react";

import { MetricCard } from "@/components/ui";
import { ApiError, fetchFromApi } from "@/lib/api";
import type { BacktestRequest, BacktestResult } from "@/lib/types";

const initialForm: BacktestRequest = {
  symbol: "AAPL",
  method: "moving",
  short_window: 10,
  long_window: 30,
  initial_capital: "10000",
  start_date: "2025-06-29",
  end_date: "2026-06-29",
};

function validate(form: BacktestRequest): string | null {
  if (!Number.isInteger(form.short_window) || form.short_window <= 0) return "Короткое окно должно быть целым числом больше нуля";
  if (!Number.isInteger(form.long_window) || form.long_window <= form.short_window) return "Длинное окно должно быть больше короткого";
  const initialCapital = Number(form.initial_capital);
  if (!Number.isFinite(initialCapital) || initialCapital <= 0) return "Условная начальная стоимость должна быть больше нуля";
  if (!form.start_date || !form.end_date || form.start_date >= form.end_date) return "Начальная дата должна быть раньше конечной";
  return null;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (Array.isArray(error.detail)) {
      const messages = error.detail.flatMap((item) => {
        if (!item || typeof item !== "object") return [];
        const message = (item as { msg?: unknown }).msg;
        return typeof message === "string" ? [message] : [];
      });
      if (messages.length) return messages.join(" · ");
    }
    return `Backend вернул ошибку HTTP ${error.status}`;
  }
  return error instanceof Error ? error.message : "Не удалось выполнить исторический расчёт";
}

function signedPercent(value: string | undefined): string {
  if (value === undefined) return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return `${value}%`;
  return `${parsed > 0 ? "+" : parsed < 0 ? "−" : ""}${Math.abs(parsed).toFixed(2)}%`;
}

function drawdownPercent(value: string | undefined): string {
  if (value === undefined) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `−${Math.abs(parsed).toFixed(2)}%` : `${value}%`;
}

function decimal(value: string | undefined): string {
  if (value === undefined) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : value;
}

function chartLines(result: BacktestResult | null): { strategy: string; benchmark: string } {
  if (!result) return { strategy: "", benchmark: "" };
  const strategy = result.strategy_curve.map(Number);
  const benchmark = result.benchmark_curve.map(Number);
  const all = [...strategy, ...benchmark].filter(Number.isFinite);
  if (!all.length || strategy.length !== benchmark.length) return { strategy: "", benchmark: "" };
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const points = (values: number[]) => values.map((value, index) => {
    const x = values.length === 1 ? 310 : index / (values.length - 1) * 620;
    const y = 168 - (value - min) / range * 150;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return { strategy: points(strategy), benchmark: points(benchmark) };
}

function dateAxis(dates: string[]): string[] {
  if (!dates.length) return [];
  const indexes = [0, Math.floor((dates.length - 1) / 3), Math.floor((dates.length - 1) * 2 / 3), dates.length - 1];
  return Array.from(new Set(indexes)).map((index) => new Intl.DateTimeFormat("ru-RU", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(dates[index])));
}

export function BacktestingWorkbench() {
  const [form, setForm] = useState<BacktestRequest>(initialForm);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const lines = useMemo(() => chartLines(result), [result]);
  const axis = useMemo(() => dateAxis(result?.dates ?? []), [result]);

  function update<K extends keyof BacktestRequest>(key: K, value: BacktestRequest[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
    setSuccess(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validate(form);
    if (validationError) {
      setError(validationError);
      setSuccess(null);
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await fetchFromApi<BacktestResult>("/backtesting/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setResult(response);
      setSuccess("Результат пересчитан");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="backtest-layout">
      <form className="panel strategy-form" onSubmit={submit} noValidate>
        <p className="eyebrow">Параметры</p>
        <h2>Настройка теста</h2>
        <label>Актив
          <select value={form.symbol} onChange={(event) => update("symbol", event.target.value)} disabled={loading}>
            <option value="AAPL">AAPL · Apple Inc.</option>
            <option value="MSFT">MSFT · Microsoft</option>
            <option value="TLT">TLT · Treasury ETF</option>
          </select>
        </label>
        <label>Метод формирования сигналов
          <select value={form.method} onChange={(event) => update("method", event.target.value as BacktestRequest["method"])} disabled={loading}>
            <option value="moving">Пересечение скользящих средних</option>
            <option value="hold">Постоянный базовый сценарий</option>
          </select>
        </label>
        <div className="field-row">
          <label>Короткое окно<input type="number" value={form.short_window} min="1" onChange={(event) => update("short_window", Number(event.target.value))} disabled={loading} /></label>
          <label>Длинное окно<input type="number" value={form.long_window} min="2" onChange={(event) => update("long_window", Number(event.target.value))} disabled={loading} /></label>
        </div>
        <label>Условная начальная стоимость (USD)<input type="number" value={form.initial_capital} min="0.01" step="0.01" onChange={(event) => update("initial_capital", event.target.value)} disabled={loading} /></label>
        <label>Период
          <div className="field-row">
            <input aria-label="Начальная дата" type="date" value={form.start_date} onChange={(event) => update("start_date", event.target.value)} disabled={loading} />
            <input aria-label="Конечная дата" type="date" value={form.end_date} onChange={(event) => update("end_date", event.target.value)} disabled={loading} />
          </div>
        </label>
        <button type="submit" className="primary-button full-width" disabled={loading}>{loading ? "Расчёт…" : "Запустить исторический тест"}</button>
        {error && <p className="backtest-message error" role="alert">{error}</p>}
        {success && <p className="backtest-message success" role="status">{success}</p>}
        <p className="ticket-warning">Используется фиксированный детерминированный демонстрационный ряд без комиссий, спредов, налогов и ограничений ликвидности.</p>
      </form>

      <div className="backtest-results">
        <section className="metrics-grid compact-metrics">
          <MetricCard label="Доходность" value={signedPercent(result?.total_return_percent)} detail={`Базовый сценарий: ${signedPercent(result?.benchmark_return_percent)}`} tone={!result ? "neutral" : Number(result.total_return_percent) >= 0 ? "positive" : "negative"} />
          <MetricCard label="Максимальная просадка" value={drawdownPercent(result?.max_drawdown_percent)} detail="Историческая аналитическая кривая" tone="negative" />
          <MetricCard label="Коэффициент Шарпа" value={decimal(result?.sharpe_ratio)} detail="Безрисковая ставка: 0%" />
          <MetricCard label="Сигналы" value={result ? String(result.signals) : "—"} detail={result ? `${result.correct_signals} верных · ${result.incorrect_signals} ошибочных` : "Запустите расчёт"} />
        </section>
        <article className="panel chart-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">Историческая кривая</p><h2>Сигналы и базовый сценарий</h2></div>
            <div className="chart-legend"><span><i />Аналитические сигналы</span><span><i />Базовый сценарий</span></div>
          </div>
          {lines.strategy && lines.benchmark ? <>
            <svg className="main-chart backtest-chart" viewBox="0 0 620 180" preserveAspectRatio="none" role="img" aria-label="Историческая динамика условной стоимости">
              <polyline points={lines.strategy} fill="none" stroke="#2dd4a8" strokeWidth="3" vectorEffect="non-scaling-stroke" />
              <polyline points={lines.benchmark} fill="none" stroke="#77839a" strokeDasharray="5 5" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            </svg>
            <div className="chart-axis">{axis.map((label, index) => <span key={`${label}-${index}`}>{label}</span>)}</div>
          </> : <div className="chart-empty">Настройте параметры и запустите исторический тест.</div>}
        </article>
        <article className="panel assumption-panel">
          <h2>Ограничения модели</h2>
          <ul><li>Только фиксированный ряд закрытий</li><li>Без комиссий и спредов</li><li>Без поправки на ошибку выжившего</li><li>Без корпоративных действий</li></ul>
        </article>
      </div>
    </section>
  );
}
