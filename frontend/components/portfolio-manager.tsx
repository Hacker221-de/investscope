"use client";

import { type ChangeEvent, type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { MetricCard } from "@/components/ui";
import { fetchMarketApi } from "@/lib/api";
import { assets, currency, positions as positionFixtures } from "@/lib/demo-data";
import type { MarketQuote, Position } from "@/lib/types";

interface LatestResponse { symbol: string; quote: MarketQuote }
interface PositionForm {
  symbol: string;
  quantity: string;
  averagePurchasePrice: string;
  purchaseDate: string;
  currency: string;
  fees: string;
}
type OwnedPosition = Omit<Position, "currentPrice" | "currentValue" | "pnl" | "weight">;
type EvaluatedPosition = OwnedPosition & {
  currentPrice?: number;
  currentValue?: number;
  pnl?: number;
  weight?: number;
  priceSource?: string;
  priceUpdatedAt?: string;
  priceIsStale?: boolean;
};

const emptyForm: PositionForm = {
  symbol: "AAPL", quantity: "", averagePurchasePrice: "", purchaseDate: "",
  currency: "USD", fees: "",
};

const initialPositions: OwnedPosition[] = positionFixtures.map((position) => ({
  id: position.id,
  symbol: position.symbol,
  quantity: position.quantity,
  averagePurchasePrice: position.averagePurchasePrice,
  purchaseDate: position.purchaseDate,
  currency: position.currency,
  fees: position.fees,
  sector: position.sector,
  geography: position.geography,
}));

function buildPosition(form: PositionForm, id: number): OwnedPosition | null {
  const symbol = form.symbol.trim().toUpperCase();
  const quantity = Number(form.quantity);
  const averagePurchasePrice = Number(form.averagePurchasePrice);
  const fees = form.fees ? Number(form.fees) : 0;
  if (!/^[A-Z0-9.-]{1,16}$/.test(symbol) || quantity <= 0 || averagePurchasePrice <= 0 || !form.purchaseDate) return null;
  const metadata = assets.find((item) => item.symbol === symbol);
  return {
    id, symbol, quantity, averagePurchasePrice, purchaseDate: form.purchaseDate,
    currency: form.currency.toUpperCase(), fees: fees || undefined,
    sector: metadata?.sector ?? "Не указан", geography: "Не указана",
  };
}

function quoteTime(quote: MarketQuote): string {
  const value = quote.received_at;
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short", timeStyle: "short", timeZone: "UTC",
  }).format(new Date(value)) + " UTC";
}

export function PortfolioManager() {
  const [positions, setPositions] = useState<OwnedPosition[]>(initialPositions);
  const [quotes, setQuotes] = useState<Record<string, MarketQuote | null>>({});
  const [quotesLoading, setQuotesLoading] = useState(true);
  const [form, setForm] = useState<PositionForm>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const symbolsKey = useMemo(
    () => [...new Set(positions.map((position) => position.symbol))].sort().join(","),
    [positions],
  );

  useEffect(() => {
    const symbols = symbolsKey ? symbolsKey.split(",") : [];
    let active = true;
    setQuotesLoading(true);
    Promise.all(symbols.map(async (symbol) => {
      try {
        const response = await fetchMarketApi<LatestResponse>(`/market/${symbol}/latest`);
        return [symbol, response.quote] as const;
      } catch {
        return [symbol, null] as const;
      }
    })).then((entries) => { if (active) setQuotes(Object.fromEntries(entries)); })
      .finally(() => { if (active) setQuotesLoading(false); });
    return () => { active = false; };
  }, [symbolsKey]);

  const evaluated: EvaluatedPosition[] = positions.map((position) => {
    const quote = quotes[position.symbol];
    if (!quote) return { ...position, currentPrice: undefined, currentValue: undefined, pnl: undefined, weight: undefined };
    const currentPrice = Number(quote.close);
    const currentValue = position.quantity * currentPrice;
    const invested = position.quantity * position.averagePurchasePrice + (position.fees ?? 0);
    return {
      ...position, currentPrice, currentValue, pnl: currentValue - invested,
      priceSource: quote.source, priceUpdatedAt: quoteTime(quote),
      priceIsStale: quote.is_fetch_stale || quote.is_market_data_stale,
    };
  });
  const valued = evaluated.filter((position) => position.currentValue !== undefined);
  const currentValue = valued.reduce((sum, position) => sum + (position.currentValue ?? 0), 0);
  const investedCapital = valued.reduce(
    (sum, position) => sum + position.quantity * position.averagePurchasePrice + (position.fees ?? 0), 0,
  );
  const recordedCapital = positions.reduce(
    (sum, position) => sum + position.quantity * position.averagePurchasePrice + (position.fees ?? 0), 0,
  );
  const unrealizedPnl = currentValue - investedCapital;
  const totalReturn = investedCapital > 0 ? unrealizedPnl / investedCapital * 100 : null;
  const unvaluedCount = positions.length - valued.length;
  const withWeights = evaluated.map((position) => ({
    ...position,
    weight: position.currentValue !== undefined && currentValue > 0
      ? position.currentValue / currentValue * 100 : undefined,
  }));

  function openCreateForm() {
    setEditingId(null); setForm(emptyForm); setMessage(""); setFormVisible(true);
  }

  function openEditForm(position: OwnedPosition) {
    setEditingId(position.id);
    setForm({
      symbol: position.symbol, quantity: String(position.quantity),
      averagePurchasePrice: String(position.averagePurchasePrice),
      purchaseDate: position.purchaseDate, currency: position.currency,
      fees: position.fees ? String(position.fees) : "",
    });
    setMessage(""); setFormVisible(true);
  }

  function submitPosition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = editingId ?? Math.max(0, ...positions.map((position) => position.id)) + 1;
    const position = buildPosition(form, id);
    if (!position) { setMessage("Проверьте тикер, количество, цену и дату покупки."); return; }
    setPositions((current) => editingId === null
      ? [...current, position]
      : current.map((item) => item.id === editingId ? position : item));
    setFormVisible(false);
    setMessage(editingId === null ? "Актив добавлен." : "Позиция изменена.");
  }

  function deletePosition(id: number) {
    setPositions((current) => current.filter((position) => position.id !== id));
    setMessage("Позиция удалена.");
    if (editingId === id) setFormVisible(false);
  }

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const rows = (await file.text()).trim().split(/\r?\n/).map((row) => row.split(","));
    const header = rows.shift()?.map((cell) => cell.trim()) ?? [];
    const required = ["symbol", "quantity", "average_purchase_price", "purchase_date", "currency"];
    if (!required.every((name) => header.includes(name))) {
      setMessage(`CSV должен содержать: ${required.join(", ")}; fees — необязательно.`);
      event.target.value = ""; return;
    }
    let nextId = Math.max(0, ...positions.map((position) => position.id)) + 1;
    const imported = rows.flatMap((row) => {
      const value = (name: string) => row[header.indexOf(name)]?.trim() ?? "";
      const position = buildPosition({
        symbol: value("symbol"), quantity: value("quantity"),
        averagePurchasePrice: value("average_purchase_price"), purchaseDate: value("purchase_date"),
        currency: value("currency"), fees: value("fees"),
      }, nextId);
      if (position) nextId += 1;
      return position ? [position] : [];
    });
    setPositions((current) => [...current, ...imported]);
    setMessage(`Импортировано позиций: ${imported.length}.`);
    event.target.value = "";
  }

  const assetAllocation = withWeights
    .flatMap((position) => position.weight === undefined ? [] : [[position.symbol, position.weight] as const])
    .sort((first, second) => second[1] - first[1]);

  function groupedAllocation(group: "sector" | "currency") {
    const labels: Record<string, string> = { Technology: "Технологии", "Fixed Income": "Облигации", Semiconductors: "Полупроводники" };
    const totals = new Map<string, number>();
    valued.forEach((position) => {
      const label = labels[position[group]] ?? position[group];
      totals.set(label, (totals.get(label) ?? 0) + (position.currentValue ?? 0));
    });
    return [...totals.entries()].map(([label, value]) => [label, currentValue > 0 ? value / currentValue * 100 : 0] as const)
      .sort((first, second) => second[1] - first[1]);
  }

  function allocationCard(title: string, items: readonly (readonly [string, number])[]) {
    return <article className="panel allocation-card"><p className="eyebrow">Распределение</p><h2>{title}</h2>{items.length ? <div className="allocation-bars">{items.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value.toFixed(1)}%</strong><i><b style={{ width: `${value}%` }} /></i></div>)}</div> : <p className="missing-value">Нет оценённых позиций.</p>}</article>;
  }

  const largestPosition = assetAllocation[0];
  const topThree = assetAllocation.slice(0, 3).reduce((sum, item) => sum + item[1], 0);
  const stressScenarios = [["Снижение рынка", -10], ["Рост ставок на 100 б.п.", -6], ["Позитивный сценарий", 5]] as const;

  return (
    <>
      <section className="metrics-grid">
        <MetricCard label="Текущая стоимость портфеля" value={valued.length ? currency.format(currentValue) : "Нет данных"} detail={`Оценено позиций: ${valued.length}`} />
        <MetricCard label="Вложенный капитал" value={valued.length ? currency.format(investedCapital) : "Нет данных"} detail={`Всего введено: ${currency.format(recordedCapital)}`} />
        <MetricCard label="Нереализованная прибыль / убыток" value={valued.length ? `${unrealizedPnl >= 0 ? "+" : ""}${currency.format(unrealizedPnl)}` : "Нет данных"} detail="Только по позициям с котировкой" tone={valued.length ? unrealizedPnl >= 0 ? "positive" : "negative" : undefined} />
        <MetricCard label="Доходность" value={totalReturn === null ? "Нет данных" : `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`} detail="Неоценённые позиции исключены" tone={totalReturn === null ? undefined : totalReturn >= 0 ? "positive" : "negative"} />
        <MetricCard label="Неоценённые позиции" value={String(unvaluedCount)} detail={quotesLoading ? "Котировки загружаются…" : "Цена отсутствует в хранилище"} tone={unvaluedCount ? "negative" : "positive"} />
      </section>

      <section className="panel positions-panel portfolio-manager">
        <div className="panel-heading portfolio-actions"><div><p className="eyebrow">Введённые пользователем данные</p><h2>Открытые позиции</h2></div><div><button className="secondary-button" onClick={() => fileInput.current?.click()}>Импорт из CSV</button><input ref={fileInput} className="visually-hidden" type="file" accept=".csv,text/csv" onChange={importCsv} /><button className="primary-button" onClick={openCreateForm}>Добавить актив</button></div></div>
        {formVisible && <form className="position-form" onSubmit={submitPosition}><div className="form-heading"><strong>{editingId === null ? "Добавить актив" : "Изменить позицию"}</strong><button type="button" onClick={() => setFormVisible(false)} aria-label="Закрыть">×</button></div><label>Тикер<input required maxLength={16} value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value.toUpperCase() })} /></label><label>Количество<input required type="number" min="0.00000001" step="0.00000001" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label><label>Средняя цена покупки<input required type="number" min="0.000001" step="0.000001" value={form.averagePurchasePrice} onChange={(event) => setForm({ ...form, averagePurchasePrice: event.target.value })} /></label><label>Дата покупки<input required type="date" value={form.purchaseDate} onChange={(event) => setForm({ ...form, purchaseDate: event.target.value })} /></label><label>Валюта<select value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })}><option>USD</option><option>EUR</option><option>GBP</option></select></label><label>Комиссия <small>необязательно</small><input type="number" min="0" step="0.0001" value={form.fees} onChange={(event) => setForm({ ...form, fees: event.target.value })} /></label><div className="form-actions"><button type="button" className="secondary-button" onClick={() => setFormVisible(false)}>Отмена</button><button type="submit" className="primary-button">Сохранить позицию</button></div></form>}
        {message && <p className="form-message" role="status">{message}</p>}
        <div className="table-wrap"><table><thead><tr><th>Актив</th><th>Количество</th><th>Средняя цена покупки</th><th>Валюта</th><th>Текущая цена</th><th>Источник / время цены</th><th>Текущая стоимость</th><th>Доля портфеля</th><th>Нереализованная прибыль / убыток</th><th>Действия</th></tr></thead><tbody>{withWeights.map((position) => <tr key={position.id}><td><span className="asset-symbol"><span className="ticker-icon">{position.symbol[0]}</span><span><strong>{position.symbol}</strong><small>{assets.find((item) => item.symbol === position.symbol)?.name ?? "Введённый актив"}</small></span></span></td><td>{position.quantity}</td><td>{currency.format(position.averagePurchasePrice)}</td><td>{position.currency}</td><td>{position.currentPrice === undefined ? <span className="unvalued-badge">Не оценена</span> : currency.format(position.currentPrice)}</td><td>{position.priceSource ? <><span className="quote-source">{position.priceSource}{position.priceIsStale && <em className="stale-badge">Устарела</em>}</span><small className="cell-note">{position.priceUpdatedAt}</small></> : "—"}</td><td>{position.currentValue === undefined ? "—" : <strong>{currency.format(position.currentValue)}</strong>}</td><td>{position.weight === undefined ? "—" : `${position.weight.toFixed(1)}%`}</td><td className={position.pnl === undefined ? "" : position.pnl >= 0 ? "positive" : "negative"}>{position.pnl === undefined ? "—" : `${position.pnl >= 0 ? "+" : ""}${currency.format(position.pnl)}`}</td><td><div className="row-actions"><button onClick={() => openEditForm(position)}>Изменить позицию</button><button className="danger-action" onClick={() => deletePosition(position.id)}>Удалить позицию</button></div></td></tr>)}</tbody></table></div>
      </section>

      <section className="portfolio-analytics-grid three-columns">{allocationCard("По активам", assetAllocation)}{allocationCard("По секторам", groupedAllocation("sector"))}{allocationCard("По валютам", groupedAllocation("currency"))}</section>
      <section className="portfolio-analytics-grid risk-grid"><article className="panel risk-overview"><p className="eyebrow">Риск-аналитика</p><h2>Исторические метрики</h2><div className="risk-stat-list"><div><span>Историческая волатильность</span><strong>21.40% · демо</strong></div><div><span>Максимальная просадка</span><strong className="negative">−4.63% · демо</strong></div><div><span>Крупнейшая позиция</span><strong>{largestPosition ? `${largestPosition[0]} · ${largestPosition[1].toFixed(2)}%` : "—"}</strong></div><div><span>Три крупнейшие позиции</span><strong>{assetAllocation.length ? `${topThree.toFixed(2)}%` : "—"}</strong></div></div></article><article className="panel correlation-panel"><p className="eyebrow">Ограничение</p><h2>Корреляция активов</h2><p>Расчёт корреляции пока использует демонстрационный ряд доходностей и не влияет на текущую оценку портфеля.</p></article></section>
      <article className="panel stress-panel dynamic-stress"><p className="eyebrow">Сценарный анализ</p><h2>Стресс-сценарии</h2>{valued.length ? <div className="table-wrap"><table><thead><tr><th>Сценарий</th><th>Шок</th><th>Стоимость оценённых позиций</th><th>Результат</th></tr></thead><tbody>{stressScenarios.map(([name, shock]) => { const projected = currentValue * (1 + shock / 100); const result = projected - investedCapital; return <tr key={name}><td>{name}</td><td className={shock >= 0 ? "positive" : "negative"}>{shock > 0 ? "+" : ""}{shock}%</td><td>{currency.format(projected)}</td><td className={result >= 0 ? "positive" : "negative"}>{result >= 0 ? "+" : ""}{currency.format(result)}</td></tr>; })}</tbody></table></div> : <p className="missing-value">Сценарий невозможно рассчитать без сохранённых котировок.</p>}</article>
    </>
  );
}
