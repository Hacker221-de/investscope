"use client";

import { type ChangeEvent, type FormEvent, useMemo, useRef, useState, useEffect } from "react";

import { MetricCard } from "@/components/ui";
import {
  ApiError,
  createPortfolio,
  createPosition,
  deletePortfolio,
  deletePosition,
  fetchMarketApi,
  formatApiError,
  getPortfolio,
  listPortfolios,
  updatePortfolio,
  updatePosition,
} from "@/lib/api";
import type {
  DecimalJson,
  MarketAsset,
  MarketQuote,
  Portfolio,
  PortfolioDetail,
  Position,
  PositionCreate,
  PositionUpdate,
} from "@/lib/types";

interface PositionForm {
  symbol: string;
  quantity: string;
  averagePurchasePrice: string;
  purchaseDate: string;
  currency: string;
  fees: string;
}

type MessageTone = "success" | "error";

type EvaluatedPosition = Position & {
  asset?: MarketAsset;
  quantityNumber: number | null;
  averagePurchasePriceNumber: number | null;
  feesNumber: number;
  currentPrice?: number;
  currentValue?: number;
  investedCapital?: number;
  pnl?: number;
  weight?: number;
  priceSource?: string;
  priceUpdatedAt?: string;
  priceIsStale?: boolean;
};

const emptyPositionForm: PositionForm = {
  symbol: "",
  quantity: "",
  averagePurchasePrice: "",
  purchaseDate: "",
  currency: "USD",
  fees: "",
};

const defaultPortfolioName = "Основной портфель";

function decimalToNumber(value: DecimalJson | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value: number, currencyCode = "USD"): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode,
      currencyDisplay: "code",
      minimumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currencyCode} ${value.toFixed(2)}`;
  }
}

function quoteTime(quote: MarketQuote): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(quote.received_at)) + " UTC";
}

function normalizeSymbol(value: string): string {
  return value.trim().toUpperCase();
}

function isPositiveDecimal(value: string): boolean {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0;
}

function isNonNegativeOptionalDecimal(value: string): boolean {
  if (!value.trim()) return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

function portfolioErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) {
    return "Позиция по этому активу уже существует в выбранном портфеле.";
  }
  return formatApiError(error);
}

export function PortfolioManager() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<number | null>(null);
  const [selectedPortfolio, setSelectedPortfolio] = useState<PortfolioDetail | null>(null);
  const [marketAssets, setMarketAssets] = useState<MarketAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingPortfolio, setSavingPortfolio] = useState(false);
  const [savingPosition, setSavingPosition] = useState(false);
  const [deletingPositionId, setDeletingPositionId] = useState<number | null>(null);
  const [portfolioName, setPortfolioName] = useState(defaultPortfolioName);
  const [renameValue, setRenameValue] = useState("");
  const [positionForm, setPositionForm] = useState<PositionForm>(emptyPositionForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formVisible, setFormVisible] = useState(false);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<MessageTone>("success");
  const fileInput = useRef<HTMLInputElement>(null);

  const assetById = useMemo(
    () => new Map(marketAssets.map((asset) => [asset.id, asset])),
    [marketAssets],
  );
  const assetBySymbol = useMemo(
    () => new Map(marketAssets.map((asset) => [asset.symbol, asset])),
    [marketAssets],
  );

  async function loadPortfolioState(preferredPortfolioId: number | null = selectedPortfolioId) {
    setLoading(true);
    setMessage("");
    try {
      const [portfolioList, assetList] = await Promise.all([
        listPortfolios(),
        fetchMarketApi<MarketAsset[]>("/assets"),
      ]);
      setPortfolios(portfolioList);
      setMarketAssets(assetList);

      const nextPortfolioId =
        preferredPortfolioId !== null && portfolioList.some((item) => item.id === preferredPortfolioId)
          ? preferredPortfolioId
          : portfolioList[0]?.id ?? null;
      setSelectedPortfolioId(nextPortfolioId);

      if (nextPortfolioId === null) {
        setSelectedPortfolio(null);
        setRenameValue("");
        return;
      }

      const detail = await getPortfolio(nextPortfolioId);
      setSelectedPortfolio(detail);
      setRenameValue(detail.name);
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
      setSelectedPortfolio(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPortfolioState(null);
    // Initial backend load only. Later changes use explicit event handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function selectPortfolio(portfolioId: number) {
    setSelectedPortfolioId(portfolioId);
    setLoading(true);
    setMessage("");
    try {
      const detail = await getPortfolio(portfolioId);
      setSelectedPortfolio(detail);
      setRenameValue(detail.name);
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
      setSelectedPortfolio(null);
    } finally {
      setLoading(false);
    }
  }

  async function submitPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = portfolioName.trim();
    if (!name) {
      setMessageTone("error");
      setMessage("Название портфеля не должно быть пустым.");
      return;
    }
    setSavingPortfolio(true);
    setMessage("");
    try {
      const created = await createPortfolio({ name, base_currency: "USD" });
      setPortfolioName(defaultPortfolioName);
      setMessageTone("success");
      setMessage("Портфель создан.");
      await loadPortfolioState(created.id);
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
    } finally {
      setSavingPortfolio(false);
    }
  }

  async function renamePortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedPortfolioId === null) return;
    const name = renameValue.trim();
    if (!name) {
      setMessageTone("error");
      setMessage("Название портфеля не должно быть пустым.");
      return;
    }
    setSavingPortfolio(true);
    setMessage("");
    try {
      const updated = await updatePortfolio(selectedPortfolioId, { name });
      setPortfolios((current) => current.map((portfolio) => (
        portfolio.id === updated.id ? updated : portfolio
      )));
      await selectPortfolio(updated.id);
      setMessageTone("success");
      setMessage("Портфель обновлён.");
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
    } finally {
      setSavingPortfolio(false);
    }
  }

  async function removeSelectedPortfolio() {
    if (selectedPortfolioId === null) return;
    const confirmed = window.confirm("Удалить выбранный портфель и все его позиции?");
    if (!confirmed) return;
    setSavingPortfolio(true);
    setMessage("");
    try {
      await deletePortfolio(selectedPortfolioId);
      setMessageTone("success");
      setMessage("Портфель удалён.");
      await loadPortfolioState(null);
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
    } finally {
      setSavingPortfolio(false);
    }
  }

  function openCreateForm() {
    const firstAssetSymbol = marketAssets[0]?.symbol ?? "";
    setEditingId(null);
    setPositionForm({ ...emptyPositionForm, symbol: firstAssetSymbol });
    setMessage("");
    setFormVisible(true);
  }

  function openEditForm(position: Position) {
    setEditingId(position.id);
    setPositionForm({
      symbol: position.symbol,
      quantity: String(position.quantity),
      averagePurchasePrice: String(position.average_purchase_price),
      purchaseDate: position.purchase_date,
      currency: position.currency,
      fees: position.fees === null ? "" : String(position.fees),
    });
    setMessage("");
    setFormVisible(true);
  }

  function buildCreatePayload(form: PositionForm): PositionCreate | null {
    const symbol = normalizeSymbol(form.symbol);
    const asset = assetBySymbol.get(symbol);
    if (!asset) {
      setMessage("Выберите актив из списка сохранённых активов.");
      return null;
    }
    if (!isPositiveDecimal(form.quantity)) {
      setMessage("Количество должно быть больше нуля.");
      return null;
    }
    if (!isNonNegativeOptionalDecimal(form.averagePurchasePrice) || !form.averagePurchasePrice.trim()) {
      setMessage("Средняя цена покупки должна быть неотрицательной.");
      return null;
    }
    if (!form.purchaseDate) {
      setMessage("Укажите дату покупки.");
      return null;
    }
    if (!/^[A-Z]{3}$/.test(form.currency.toUpperCase())) {
      setMessage("Валюта должна состоять из трёх латинских букв.");
      return null;
    }
    if (!isNonNegativeOptionalDecimal(form.fees)) {
      setMessage("Комиссия не может быть отрицательной.");
      return null;
    }
    return {
      asset_id: asset.id,
      quantity: form.quantity.trim(),
      average_purchase_price: form.averagePurchasePrice.trim(),
      purchase_date: form.purchaseDate,
      currency: form.currency.toUpperCase(),
      fees: form.fees.trim() ? form.fees.trim() : null,
    };
  }

  function buildUpdatePayload(form: PositionForm): PositionUpdate | null {
    if (!isPositiveDecimal(form.quantity)) {
      setMessage("Количество должно быть больше нуля.");
      return null;
    }
    if (!isNonNegativeOptionalDecimal(form.averagePurchasePrice) || !form.averagePurchasePrice.trim()) {
      setMessage("Средняя цена покупки должна быть неотрицательной.");
      return null;
    }
    if (!form.purchaseDate) {
      setMessage("Укажите дату покупки.");
      return null;
    }
    if (!/^[A-Z]{3}$/.test(form.currency.toUpperCase())) {
      setMessage("Валюта должна состоять из трёх латинских букв.");
      return null;
    }
    if (!isNonNegativeOptionalDecimal(form.fees)) {
      setMessage("Комиссия не может быть отрицательной.");
      return null;
    }
    return {
      quantity: form.quantity.trim(),
      average_purchase_price: form.averagePurchasePrice.trim(),
      purchase_date: form.purchaseDate,
      currency: form.currency.toUpperCase(),
      fees: form.fees.trim() ? form.fees.trim() : null,
    };
  }

  async function submitPosition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedPortfolioId === null) return;
    setSavingPosition(true);
    setMessage("");
    setMessageTone("error");
    try {
      if (editingId === null) {
        const payload = buildCreatePayload(positionForm);
        if (payload === null) return;
        await createPosition(selectedPortfolioId, payload);
        setMessageTone("success");
        setMessage("Актив добавлен.");
      } else {
        const payload = buildUpdatePayload(positionForm);
        if (payload === null) return;
        await updatePosition(selectedPortfolioId, editingId, payload);
        setMessageTone("success");
        setMessage("Позиция изменена.");
      }
      setFormVisible(false);
      setEditingId(null);
      await loadPortfolioState(selectedPortfolioId);
    } catch (error) {
      setMessageTone("error");
      setMessage(portfolioErrorMessage(error));
    } finally {
      setSavingPosition(false);
    }
  }

  async function removePosition(id: number) {
    if (selectedPortfolioId === null) return;
    setDeletingPositionId(id);
    setMessage("");
    try {
      await deletePosition(selectedPortfolioId, id);
      setMessageTone("success");
      setMessage("Позиция удалена.");
      if (editingId === id) {
        setFormVisible(false);
        setEditingId(null);
      }
      await loadPortfolioState(selectedPortfolioId);
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error));
    } finally {
      setDeletingPositionId(null);
    }
  }

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || selectedPortfolioId === null) return;
    const required = ["symbol", "quantity", "average_purchase_price", "purchase_date", "currency"];
    setSavingPosition(true);
    setMessage("");
    try {
      const rows = (await file.text()).trim().split(/\r?\n/).filter(Boolean).map((row) => row.split(","));
      const header = rows.shift()?.map((cell) => cell.trim()) ?? [];
      if (!required.every((name) => header.includes(name))) {
        setMessageTone("error");
        setMessage(`CSV должен содержать: ${required.join(", ")}; fees — необязательно.`);
        return;
      }

      let imported = 0;
      const errors: string[] = [];
      for (const [index, row] of rows.entries()) {
        const value = (name: string) => row[header.indexOf(name)]?.trim() ?? "";
        const symbol = normalizeSymbol(value("symbol"));
        const asset = assetBySymbol.get(symbol);
        if (!asset) {
          errors.push(`строка ${index + 2}: актив ${symbol || "—"} не найден`);
          continue;
        }
        try {
          await createPosition(selectedPortfolioId, {
            asset_id: asset.id,
            quantity: value("quantity"),
            average_purchase_price: value("average_purchase_price"),
            purchase_date: value("purchase_date"),
            currency: value("currency").toUpperCase(),
            fees: value("fees") || null,
          });
          imported += 1;
        } catch (error) {
          errors.push(`строка ${index + 2}: ${portfolioErrorMessage(error)}`);
        }
      }
      await loadPortfolioState(selectedPortfolioId);
      setMessageTone(errors.length ? "error" : "success");
      setMessage(
        errors.length
          ? `Импортировано позиций: ${imported}. Ошибки: ${errors.join("; ")}`
          : `Импортировано позиций: ${imported}.`,
      );
    } catch (error) {
      setMessageTone("error");
      setMessage(formatApiError(error, "Не удалось прочитать CSV-файл."));
    } finally {
      event.target.value = "";
      setSavingPosition(false);
    }
  }

  const evaluated: EvaluatedPosition[] = useMemo(() => (
    (selectedPortfolio?.positions ?? []).map((position) => {
      const asset = assetById.get(position.asset_id) ?? assetBySymbol.get(position.symbol);
      const quote = asset?.latest_quote ?? null;
      const quantity = decimalToNumber(position.quantity);
      const averagePurchasePrice = decimalToNumber(position.average_purchase_price);
      const fees = decimalToNumber(position.fees) ?? 0;
      const currentPrice = quote ? decimalToNumber(quote.close) : null;
      const investedCapital = quantity !== null && averagePurchasePrice !== null
        ? quantity * averagePurchasePrice + fees
        : undefined;
      const currentValue = quantity !== null && currentPrice !== null
        ? quantity * currentPrice
        : undefined;
      const pnl = currentValue !== undefined && investedCapital !== undefined
        ? currentValue - investedCapital
        : undefined;
      return {
        ...position,
        asset,
        quantityNumber: quantity,
        averagePurchasePriceNumber: averagePurchasePrice,
        feesNumber: fees,
        currentPrice: currentPrice ?? undefined,
        currentValue,
        investedCapital,
        pnl,
        priceSource: quote?.source,
        priceUpdatedAt: quote ? quoteTime(quote) : undefined,
        priceIsStale: quote ? quote.is_fetch_stale || quote.is_market_data_stale : undefined,
      };
    })
  ), [assetById, assetBySymbol, selectedPortfolio]);

  const valued = evaluated.filter((position) => position.currentValue !== undefined);
  const currentValue = valued.reduce((sum, position) => sum + (position.currentValue ?? 0), 0);
  const investedCapital = valued.reduce((sum, position) => sum + (position.investedCapital ?? 0), 0);
  const recordedCapital = evaluated.reduce((sum, position) => sum + (position.investedCapital ?? 0), 0);
  const unrealizedPnl = currentValue - investedCapital;
  const totalReturn = investedCapital > 0 ? unrealizedPnl / investedCapital * 100 : null;
  const unvaluedCount = evaluated.length - valued.length;
  const withWeights = evaluated.map((position) => ({
    ...position,
    weight: position.currentValue !== undefined && currentValue > 0
      ? position.currentValue / currentValue * 100
      : undefined,
  }));

  const assetAllocation = withWeights
    .flatMap((position) => position.weight === undefined ? [] : [[position.symbol, position.weight] as const])
    .sort((first, second) => second[1] - first[1]);

  function groupedAllocation(group: "sector" | "currency") {
    const labels: Record<string, string> = {
      Technology: "Технологии",
      "Fixed Income": "Облигации",
      Semiconductors: "Полупроводники",
    };
    const totals = new Map<string, number>();
    valued.forEach((position) => {
      const labelValue = group === "sector"
        ? position.asset?.sector ?? "Не указан"
        : position.currency;
      const label = labels[labelValue] ?? labelValue;
      totals.set(label, (totals.get(label) ?? 0) + (position.currentValue ?? 0));
    });
    return [...totals.entries()]
      .map(([label, value]) => [label, currentValue > 0 ? value / currentValue * 100 : 0] as const)
      .sort((first, second) => second[1] - first[1]);
  }

  function allocationCard(title: string, items: readonly (readonly [string, number])[]) {
    return (
      <article className="panel allocation-card">
        <p className="eyebrow">Распределение</p>
        <h2>{title}</h2>
        {items.length ? (
          <div className="allocation-bars">
            {items.map(([label, value]) => (
              <div key={label}>
                <span>{label}</span>
                <strong>{value.toFixed(1)}%</strong>
                <i><b style={{ width: `${value}%` }} /></i>
              </div>
            ))}
          </div>
        ) : (
          <p className="missing-value">Нет оценённых позиций.</p>
        )}
      </article>
    );
  }

  const largestPosition = assetAllocation[0];
  const topThree = assetAllocation.slice(0, 3).reduce((sum, item) => sum + item[1], 0);
  const stressScenarios = [
    ["Снижение рынка", -10],
    ["Рост ставок на 100 б.п.", -6],
    ["Позитивный сценарий", 5],
  ] as const;

  if (loading && portfolios.length === 0) {
    return <section className="panel positions-panel"><p className="market-message">Загрузка портфелей…</p></section>;
  }

  const hasPortfolio = selectedPortfolioId !== null && selectedPortfolio !== null;

  return (
    <>
      <section className="panel positions-panel portfolio-manager">
        <div className="panel-heading portfolio-actions">
          <div>
            <p className="eyebrow">Портфели из базы данных</p>
            <h2>Управление портфелем</h2>
          </div>
          <form className="portfolio-create-form" onSubmit={submitPortfolio}>
            <input
              aria-label="Название нового портфеля"
              maxLength={120}
              value={portfolioName}
              onChange={(event) => setPortfolioName(event.target.value)}
            />
            <button className="primary-button" type="submit" disabled={savingPortfolio}>
              {savingPortfolio ? "Сохранение…" : "Создать портфель"}
            </button>
          </form>
        </div>

        {portfolios.length > 0 ? (
          <div className="portfolio-selector">
            <label>
              Выбранный портфель
              <select
                value={selectedPortfolioId ?? ""}
                disabled={loading || savingPortfolio}
                onChange={(event) => void selectPortfolio(Number(event.target.value))}
              >
                {portfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name} · {portfolio.base_currency}
                  </option>
                ))}
              </select>
            </label>
            <form onSubmit={renamePortfolio}>
              <input
                aria-label="Новое название портфеля"
                maxLength={120}
                value={renameValue}
                onChange={(event) => setRenameValue(event.target.value)}
              />
              <button className="secondary-button" type="submit" disabled={savingPortfolio || !hasPortfolio}>
                Переименовать
              </button>
            </form>
            <button
              className="secondary-button danger-action"
              type="button"
              disabled={savingPortfolio || !hasPortfolio}
              onClick={() => void removeSelectedPortfolio()}
            >
              Удалить портфель
            </button>
          </div>
        ) : (
          <div className="portfolio-empty-state">
            <span>Портфели ещё не созданы</span>
            <p>Создайте портфель, затем добавьте активы, которыми вы фактически владеете.</p>
          </div>
        )}

        {message && (
          <p className={`form-message ${messageTone === "error" ? "error" : ""}`} role="status">
            {message}
          </p>
        )}
      </section>

      {hasPortfolio && (
        <>
          <section className="metrics-grid">
            <MetricCard
              label="Текущая стоимость портфеля"
              value={valued.length ? money(currentValue, selectedPortfolio.base_currency) : "Нет данных"}
              detail={`Оценено позиций: ${valued.length}`}
            />
            <MetricCard
              label="Вложенный капитал"
              value={valued.length ? money(investedCapital, selectedPortfolio.base_currency) : "Нет данных"}
              detail={`Всего введено: ${money(recordedCapital, selectedPortfolio.base_currency)}`}
            />
            <MetricCard
              label="Нереализованная прибыль / убыток"
              value={valued.length ? `${unrealizedPnl >= 0 ? "+" : ""}${money(unrealizedPnl, selectedPortfolio.base_currency)}` : "Нет данных"}
              detail="Только по позициям с котировкой"
              tone={valued.length ? unrealizedPnl >= 0 ? "positive" : "negative" : undefined}
            />
            <MetricCard
              label="Доходность"
              value={totalReturn === null ? "Нет данных" : `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`}
              detail="Неоценённые позиции исключены"
              tone={totalReturn === null ? undefined : totalReturn >= 0 ? "positive" : "negative"}
            />
            <MetricCard
              label="Неоценённые позиции"
              value={String(unvaluedCount)}
              detail="Цена отсутствует в сохранённых котировках"
              tone={unvaluedCount ? "negative" : "positive"}
            />
          </section>

          <section className="panel positions-panel portfolio-manager">
            <div className="panel-heading portfolio-actions">
              <div>
                <p className="eyebrow">Введённые пользователем данные</p>
                <h2>Открытые позиции</h2>
              </div>
              <div>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={savingPosition || marketAssets.length === 0}
                  onClick={() => fileInput.current?.click()}
                >
                  Импорт из CSV
                </button>
                <input
                  ref={fileInput}
                  className="visually-hidden"
                  type="file"
                  accept=".csv,text/csv"
                  onChange={importCsv}
                />
                <button
                  className="primary-button"
                  type="button"
                  disabled={marketAssets.length === 0}
                  onClick={openCreateForm}
                >
                  Добавить актив
                </button>
              </div>
            </div>

            {marketAssets.length === 0 && (
              <p className="market-message error">
                Список активов пуст. Сначала синхронизируйте или загрузите активы в backend.
              </p>
            )}

            {formVisible && (
              <form className="position-form" onSubmit={submitPosition}>
                <div className="form-heading">
                  <strong>{editingId === null ? "Добавить актив" : "Изменить позицию"}</strong>
                  <button type="button" onClick={() => setFormVisible(false)} aria-label="Закрыть">×</button>
                </div>
                <label>
                  Актив
                  <input
                    required
                    list="portfolio-assets"
                    maxLength={16}
                    disabled={editingId !== null}
                    value={positionForm.symbol}
                    onChange={(event) => setPositionForm({
                      ...positionForm,
                      symbol: event.target.value.toUpperCase(),
                    })}
                  />
                  <datalist id="portfolio-assets">
                    {marketAssets.map((asset) => (
                      <option key={asset.id} value={asset.symbol}>
                        {asset.name}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label>
                  Количество
                  <input
                    required
                    inputMode="decimal"
                    min="0.00000001"
                    step="0.00000001"
                    type="number"
                    value={positionForm.quantity}
                    onChange={(event) => setPositionForm({ ...positionForm, quantity: event.target.value })}
                  />
                </label>
                <label>
                  Средняя цена покупки
                  <input
                    required
                    inputMode="decimal"
                    min="0"
                    step="0.000001"
                    type="number"
                    value={positionForm.averagePurchasePrice}
                    onChange={(event) => setPositionForm({
                      ...positionForm,
                      averagePurchasePrice: event.target.value,
                    })}
                  />
                </label>
                <label>
                  Дата покупки
                  <input
                    required
                    type="date"
                    value={positionForm.purchaseDate}
                    onChange={(event) => setPositionForm({
                      ...positionForm,
                      purchaseDate: event.target.value,
                    })}
                  />
                </label>
                <label>
                  Валюта
                  <select
                    value={positionForm.currency}
                    onChange={(event) => setPositionForm({ ...positionForm, currency: event.target.value })}
                  >
                    <option>USD</option>
                    <option>EUR</option>
                    <option>GBP</option>
                  </select>
                </label>
                <label>
                  Комиссия <small>необязательно</small>
                  <input
                    inputMode="decimal"
                    min="0"
                    step="0.0001"
                    type="number"
                    value={positionForm.fees}
                    onChange={(event) => setPositionForm({ ...positionForm, fees: event.target.value })}
                  />
                </label>
                <div className="form-actions">
                  <button type="button" className="secondary-button" onClick={() => setFormVisible(false)}>
                    Отмена
                  </button>
                  <button type="submit" className="primary-button" disabled={savingPosition}>
                    {savingPosition ? "Сохранение…" : "Сохранить позицию"}
                  </button>
                </div>
              </form>
            )}

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Актив</th>
                    <th>Количество</th>
                    <th>Средняя цена покупки</th>
                    <th>Валюта</th>
                    <th>Текущая цена</th>
                    <th>Источник / время цены</th>
                    <th>Текущая стоимость</th>
                    <th>Доля портфеля</th>
                    <th>Нереализованная прибыль / убыток</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {withWeights.length ? withWeights.map((position) => (
                    <tr key={position.id}>
                      <td>
                        <span className="asset-symbol">
                          <span className="ticker-icon">{position.symbol[0]}</span>
                          <span>
                            <strong>{position.symbol}</strong>
                            <small>{position.asset?.name ?? "Сохранённый актив"}</small>
                          </span>
                        </span>
                      </td>
                      <td>{String(position.quantity)}</td>
                      <td>
                        {position.averagePurchasePriceNumber === null
                          ? "—"
                          : money(position.averagePurchasePriceNumber, position.currency)}
                      </td>
                      <td>{position.currency}</td>
                      <td>
                        {position.currentPrice === undefined ? (
                          <span className="unvalued-badge">Не оценена</span>
                        ) : (
                          money(position.currentPrice, position.asset?.latest_quote?.currency ?? position.currency)
                        )}
                      </td>
                      <td>
                        {position.priceSource ? (
                          <>
                            <span className="quote-source">
                              {position.priceSource}
                              {position.priceIsStale && <em className="stale-badge">Устарела</em>}
                            </span>
                            <small className="cell-note">{position.priceUpdatedAt}</small>
                          </>
                        ) : "—"}
                      </td>
                      <td>
                        {position.currentValue === undefined
                          ? "—"
                          : <strong>{money(position.currentValue, selectedPortfolio.base_currency)}</strong>}
                      </td>
                      <td>{position.weight === undefined ? "—" : `${position.weight.toFixed(1)}%`}</td>
                      <td className={position.pnl === undefined ? "" : position.pnl >= 0 ? "positive" : "negative"}>
                        {position.pnl === undefined
                          ? "—"
                          : `${position.pnl >= 0 ? "+" : ""}${money(position.pnl, selectedPortfolio.base_currency)}`}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button type="button" onClick={() => openEditForm(position)}>
                            Изменить позицию
                          </button>
                          <button
                            className="danger-action"
                            type="button"
                            disabled={deletingPositionId === position.id}
                            onClick={() => void removePosition(position.id)}
                          >
                            {deletingPositionId === position.id ? "Удаление…" : "Удалить позицию"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan={10}>
                        <p className="missing-value">В этом портфеле пока нет позиций.</p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="portfolio-analytics-grid three-columns">
            {allocationCard("По активам", assetAllocation)}
            {allocationCard("По секторам", groupedAllocation("sector"))}
            {allocationCard("По валютам", groupedAllocation("currency"))}
          </section>

          <section className="portfolio-analytics-grid risk-grid">
            <article className="panel risk-overview">
              <p className="eyebrow">Риск-аналитика</p>
              <h2>Исторические метрики</h2>
              <div className="risk-stat-list">
                <div><span>Историческая волатильность</span><strong>21.40% · демо</strong></div>
                <div><span>Максимальная просадка</span><strong className="negative">−4.63% · демо</strong></div>
                <div>
                  <span>Крупнейшая позиция</span>
                  <strong>{largestPosition ? `${largestPosition[0]} · ${largestPosition[1].toFixed(2)}%` : "—"}</strong>
                </div>
                <div>
                  <span>Три крупнейшие позиции</span>
                  <strong>{assetAllocation.length ? `${topThree.toFixed(2)}%` : "—"}</strong>
                </div>
              </div>
            </article>
            <article className="panel correlation-panel">
              <p className="eyebrow">Ограничение</p>
              <h2>Корреляция активов</h2>
              <p>Расчёт корреляции пока использует демонстрационный ряд доходностей и не влияет на текущую оценку портфеля.</p>
            </article>
          </section>

          <article className="panel stress-panel dynamic-stress">
            <p className="eyebrow">Сценарный анализ</p>
            <h2>Стресс-сценарии</h2>
            {valued.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Сценарий</th>
                      <th>Шок</th>
                      <th>Стоимость оценённых позиций</th>
                      <th>Результат</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stressScenarios.map(([name, shock]) => {
                      const projected = currentValue * (1 + shock / 100);
                      const result = projected - investedCapital;
                      return (
                        <tr key={name}>
                          <td>{name}</td>
                          <td className={shock >= 0 ? "positive" : "negative"}>{shock > 0 ? "+" : ""}{shock}%</td>
                          <td>{money(projected, selectedPortfolio.base_currency)}</td>
                          <td className={result >= 0 ? "positive" : "negative"}>
                            {result >= 0 ? "+" : ""}{money(result, selectedPortfolio.base_currency)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="missing-value">Сценарий невозможно рассчитать без сохранённых котировок.</p>
            )}
          </article>
        </>
      )}
    </>
  );
}
