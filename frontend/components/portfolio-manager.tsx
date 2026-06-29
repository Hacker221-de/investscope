"use client";

import { type ChangeEvent, type FormEvent, useRef, useState } from "react";

import { MetricCard } from "@/components/ui";
import { assets, currency, positions as initialPositions } from "@/lib/demo-data";
import type { Position } from "@/lib/types";

interface PositionForm {
  symbol: string;
  quantity: string;
  averagePurchasePrice: string;
  purchaseDate: string;
  currency: string;
  fees: string;
}

const emptyForm: PositionForm = {
  symbol: "AAPL",
  quantity: "",
  averagePurchasePrice: "",
  purchaseDate: "",
  currency: "USD",
  fees: "",
};

function withWeights(positions: Position[]): Position[] {
  const total = positions.reduce((sum, position) => sum + position.currentValue, 0);
  return positions.map((position) => ({
    ...position,
    weight: total > 0 ? (position.currentValue / total) * 100 : 0,
  }));
}

function buildPosition(form: PositionForm, id: number): Position | null {
  const asset = assets.find((item) => item.symbol === form.symbol.trim().toUpperCase());
  const quantity = Number(form.quantity);
  const averagePurchasePrice = Number(form.averagePurchasePrice);
  const fees = form.fees ? Number(form.fees) : 0;
  if (!asset || quantity <= 0 || averagePurchasePrice <= 0 || !form.purchaseDate) return null;
  const currentValue = quantity * asset.price;
  const investedCapital = quantity * averagePurchasePrice + fees;
  return {
    id,
    symbol: asset.symbol,
    quantity,
    averagePurchasePrice,
    purchaseDate: form.purchaseDate,
    currency: form.currency.toUpperCase(),
    fees: fees || undefined,
    sector: asset.sector,
    geography: "United States",
    currentPrice: asset.price,
    currentValue,
    pnl: currentValue - investedCapital,
    weight: 0,
  };
}

export function PortfolioManager() {
  const [positions, setPositions] = useState<Position[]>(initialPositions);
  const [form, setForm] = useState<PositionForm>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyForm);
    setMessage("");
    setFormVisible(true);
  }

  function openEditForm(position: Position) {
    setEditingId(position.id);
    setForm({
      symbol: position.symbol,
      quantity: String(position.quantity),
      averagePurchasePrice: String(position.averagePurchasePrice),
      purchaseDate: position.purchaseDate,
      currency: position.currency,
      fees: position.fees ? String(position.fees) : "",
    });
    setMessage("");
    setFormVisible(true);
  }

  function submitPosition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = editingId ?? Math.max(0, ...positions.map((position) => position.id)) + 1;
    const position = buildPosition(form, id);
    if (!position) {
      setMessage("Проверьте символ, количество, цену и дату покупки.");
      return;
    }
    setPositions((current) => withWeights(
      editingId === null
        ? [...current, position]
        : current.map((item) => item.id === editingId ? position : item),
    ));
    setFormVisible(false);
    setMessage(editingId === null ? "Актив добавлен." : "Позиция изменена.");
  }

  function deletePosition(id: number) {
    setPositions((current) => withWeights(current.filter((position) => position.id !== id)));
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
      event.target.value = "";
      return;
    }
    let nextId = Math.max(0, ...positions.map((position) => position.id)) + 1;
    const imported = rows.flatMap((row) => {
      const value = (name: string) => row[header.indexOf(name)]?.trim() ?? "";
      const position = buildPosition({
        symbol: value("symbol"),
        quantity: value("quantity"),
        averagePurchasePrice: value("average_purchase_price"),
        purchaseDate: value("purchase_date"),
        currency: value("currency"),
        fees: value("fees"),
      }, nextId);
      if (position) nextId += 1;
      return position ? [position] : [];
    });
    setPositions((current) => withWeights([...current, ...imported]));
    setMessage(`Импортировано позиций: ${imported.length}.`);
    event.target.value = "";
  }

  const currentValue = positions.reduce((sum, position) => sum + position.currentValue, 0);
  const investedCapital = positions.reduce(
    (sum, position) => sum + position.quantity * position.averagePurchasePrice + (position.fees ?? 0),
    0,
  );
  const unrealizedPnl = currentValue - investedCapital;
  const totalReturn = investedCapital > 0 ? (unrealizedPnl / investedCapital) * 100 : 0;
  const assetAllocation = positions
    .map((position) => [position.symbol, position.weight] as const)
    .sort((first, second) => second[1] - first[1]);

  function groupedAllocation(group: "sector" | "currency") {
    const totals = new Map<string, number>();
    positions.forEach((position) => totals.set(
      position[group],
      (totals.get(position[group]) ?? 0) + position.currentValue,
    ));
    return [...totals.entries()]
      .map(([label, value]) => [label, currentValue > 0 ? value / currentValue * 100 : 0] as const)
      .sort((first, second) => second[1] - first[1]);
  }

  function allocationCard(title: string, items: readonly (readonly [string, number])[]) {
    return <article className="panel allocation-card"><p className="eyebrow">Распределение</p><h2>{title}</h2><div className="allocation-bars">{items.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value.toFixed(1)}%</strong><i><b style={{ width: `${value}%` }} /></i></div>)}</div></article>;
  }

  const correlationDefaults = new Map([
    ["AAPL:MSFT", 0.74], ["AAPL:TLT", -0.18], ["MSFT:TLT", -0.12],
  ]);
  const correlations = positions.flatMap((first, firstIndex) => positions.slice(firstIndex + 1).map((second) => {
    const key = [first.symbol, second.symbol].sort().join(":");
    return { first: first.symbol, second: second.symbol, value: correlationDefaults.get(key) ?? 0.25 };
  }));
  const largestPosition = assetAllocation[0];
  const topThree = assetAllocation.slice(0, 3).reduce((sum, item) => sum + item[1], 0);
  const stressScenarios = [
    ["Снижение рынка", -10], ["Рост ставок на 100 б.п.", -6], ["Позитивный сезон отчётности", 5],
  ] as const;

  return (
    <>
      <section className="metrics-grid">
        <MetricCard label="Текущая стоимость портфеля" value={currency.format(currentValue)} detail="По введённым позициям" />
        <MetricCard label="Вложенный капитал" value={currency.format(investedCapital)} detail="С учётом комиссий" />
        <MetricCard label="Нереализованная прибыль / убыток" value={`${unrealizedPnl >= 0 ? "+" : ""}${currency.format(unrealizedPnl)}`} detail="По текущим аналитическим ценам" tone={unrealizedPnl >= 0 ? "positive" : "negative"} />
        <MetricCard label="Доходность" value={`${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`} detail="От вложенного капитала" tone={totalReturn >= 0 ? "positive" : "negative"} />
      </section>

      <section className="panel positions-panel portfolio-manager">
      <div className="panel-heading portfolio-actions">
        <div><p className="eyebrow">Введённые пользователем данные</p><h2>Открытые позиции</h2></div>
        <div>
          <button className="secondary-button" onClick={() => fileInput.current?.click()}>Импорт из CSV</button>
          <input ref={fileInput} className="visually-hidden" type="file" accept=".csv,text/csv" onChange={importCsv} />
          <button className="primary-button" onClick={openCreateForm}>Добавить актив</button>
        </div>
      </div>

      {formVisible && (
        <form className="position-form" onSubmit={submitPosition}>
          <div className="form-heading"><strong>{editingId === null ? "Добавить актив" : "Изменить позицию"}</strong><button type="button" onClick={() => setFormVisible(false)} aria-label="Закрыть">×</button></div>
          <label>Symbol<select value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value })}>{assets.map((asset) => <option key={asset.symbol} value={asset.symbol}>{asset.symbol} · {asset.name}</option>)}</select></label>
          <label>Quantity<input required type="number" min="0.00000001" step="0.00000001" value={form.quantity} onChange={(event) => setForm({ ...form, quantity: event.target.value })} /></label>
          <label>Average purchase price<input required type="number" min="0.000001" step="0.000001" value={form.averagePurchasePrice} onChange={(event) => setForm({ ...form, averagePurchasePrice: event.target.value })} /></label>
          <label>Purchase date<input required type="date" value={form.purchaseDate} onChange={(event) => setForm({ ...form, purchaseDate: event.target.value })} /></label>
          <label>Currency<select value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })}><option>USD</option><option>EUR</option><option>GBP</option></select></label>
          <label>Fees <small>необязательно</small><input type="number" min="0" step="0.0001" value={form.fees} onChange={(event) => setForm({ ...form, fees: event.target.value })} /></label>
          <div className="form-actions"><button type="button" className="secondary-button" onClick={() => setFormVisible(false)}>Отмена</button><button type="submit" className="primary-button">Сохранить позицию</button></div>
        </form>
      )}

      {message && <p className="form-message" role="status">{message}</p>}
      <div className="table-wrap"><table><thead><tr><th>Актив</th><th>Количество</th><th>Средняя цена покупки</th><th>Дата покупки</th><th>Валюта</th><th>Комиссии</th><th>Текущая стоимость</th><th>Вес</th><th>Нереализованная прибыль / убыток</th><th>Действия</th></tr></thead><tbody>
        {positions.map((position) => <tr key={position.id}><td><span className="asset-symbol"><span className="ticker-icon">{position.symbol[0]}</span><span><strong>{position.symbol}</strong><small>{assets.find((item) => item.symbol === position.symbol)?.name}</small></span></span></td><td>{position.quantity}</td><td>{currency.format(position.averagePurchasePrice)}</td><td>{position.purchaseDate}</td><td>{position.currency}</td><td>{position.fees ? currency.format(position.fees) : "—"}</td><td><strong>{currency.format(position.currentValue)}</strong></td><td>{position.weight.toFixed(1)}%</td><td className={position.pnl >= 0 ? "positive" : "negative"}>{position.pnl >= 0 ? "+" : ""}{currency.format(position.pnl)}</td><td><div className="row-actions"><button onClick={() => openEditForm(position)}>Изменить позицию</button><button className="danger-action" onClick={() => deletePosition(position.id)}>Удалить позицию</button></div></td></tr>)}
      </tbody></table></div>
      </section>

      <section className="portfolio-analytics-grid three-columns">
        {allocationCard("По активам", assetAllocation)}
        {allocationCard("По секторам", groupedAllocation("sector"))}
        {allocationCard("По валютам", groupedAllocation("currency"))}
      </section>

      <section className="portfolio-analytics-grid risk-grid">
        <article className="panel risk-overview"><p className="eyebrow">Риск-аналитика</p><h2>Исторические метрики</h2><div className="risk-stat-list"><div><span>Историческая волатильность</span><strong>21.40%</strong></div><div><span>Максимальная просадка</span><strong className="negative">−4.63%</strong></div><div><span>Крупнейшая позиция</span><strong>{largestPosition ? `${largestPosition[0]} · ${largestPosition[1].toFixed(2)}%` : "—"}</strong></div><div><span>Три крупнейшие позиции</span><strong>{topThree.toFixed(2)}%</strong></div></div></article>
        <article className="panel correlation-panel"><p className="eyebrow">Диверсификация</p><h2>Корреляция активов</h2>{correlations.length > 0 ? <table className="correlation-table"><thead><tr><th>Первая позиция</th><th>Вторая позиция</th><th>Коэффициент</th></tr></thead><tbody>{correlations.map((item) => <tr key={`${item.first}-${item.second}`}><td>{item.first}</td><td>{item.second}</td><td className={Math.abs(item.value) >= .7 ? "corr-high" : "corr-low"}>{item.value.toFixed(2)}</td></tr>)}</tbody></table> : <p>Для расчёта нужны минимум две позиции.</p>}<p>Расчёт основан на демонстрационном историческом ряде доходностей.</p></article>
      </section>

      <article className="panel stress-panel dynamic-stress"><p className="eyebrow">Сценарный анализ</p><h2>Стресс-сценарии</h2><div className="table-wrap"><table><thead><tr><th>Сценарий</th><th>Шок</th><th>Стоимость</th><th>Результат</th></tr></thead><tbody>{stressScenarios.map(([name, shock]) => { const projected = currentValue * (1 + shock / 100); const result = projected - investedCapital; return <tr key={name}><td>{name}</td><td className={shock >= 0 ? "positive" : "negative"}>{shock > 0 ? "+" : ""}{shock}%</td><td>{currency.format(projected)}</td><td className={result >= 0 ? "positive" : "negative"}>{result >= 0 ? "+" : ""}{currency.format(result)}</td></tr>; })}</tbody></table></div></article>
    </>
  );
}
