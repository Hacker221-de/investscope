export type Trend = "up" | "down" | "flat";
export type Rating = "BUY" | "HOLD" | "SELL";

export interface Asset {
  symbol: string;
  name: string;
  type: "Equity" | "ETF";
  sector: string;
  price: number;
  change: number;
  fairValue: number;
  rating: Rating;
}

export interface Position {
  id: number;
  symbol: string;
  quantity: number;
  averagePurchasePrice: number;
  purchaseDate: string;
  currency: string;
  fees?: number;
  sector: string;
  geography: string;
  currentPrice: number;
  currentValue: number;
  pnl: number;
  weight: number;
}

export interface MarketQuote {
  close: string;
  previous_close: string | null;
  change: string | null;
  change_percent: string | null;
  currency: string;
  source: string;
  event_time: string;
  published_at: string | null;
  received_at: string;
  is_fetch_stale: boolean;
  is_market_data_stale: boolean;
  is_stale: boolean;
}

export interface MarketAsset {
  id: number;
  symbol: string;
  name: string;
  asset_type: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  currency: string;
  provider_symbol: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  latest_quote: MarketQuote | null;
}

export interface MarketBar {
  timeframe: string;
  event_time: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  adjusted_close: string | null;
  volume: number | null;
  provider: string;
  published_at: string | null;
  received_at: string;
}

export interface MarketSyncResult {
  provider: string;
  symbol: string;
  inserted: number;
  updated: number;
  rejected: number;
  skipped: boolean;
  reason: string | null;
  skip_reason: string | null;
  latest_event_time: string | null;
  latest_received_at: string | null;
  requests_used_today: number;
  daily_limit: number | null;
  received_at: string;
}

export interface ProviderMarketDataStatus {
  configured_provider: string;
  available: boolean;
  requests_used_today: number;
  daily_limit: number | null;
  remaining_requests: number | null;
  last_request_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  data_stale_after_hours: number;
}

export interface BacktestRequest {
  symbol: string;
  method: "moving" | "hold";
  short_window: number;
  long_window: number;
  initial_capital: string;
  start_date: string;
  end_date: string;
}

export interface BacktestResult {
  symbol: string;
  method: "moving" | "hold";
  start_date: string;
  end_date: string;
  final_value: string;
  benchmark_final_value: string;
  total_return_percent: string;
  benchmark_return_percent: string;
  max_drawdown_percent: string;
  sharpe_ratio: string;
  signals: number;
  correct_signals: number;
  incorrect_signals: number;
  dates: string[];
  strategy_curve: string[];
  benchmark_curve: string[];
  note: string;
}

export type FundamentalPeriodType = "quarterly" | "annual" | "ttm";

export type FundamentalIngestionMethod = "api" | "manual_json" | string;
export type FundamentalMetricStatus = "available" | "unavailable" | string;

export interface FundamentalCompanyProfile {
  id: number;
  asset_id: number;
  provider: string;
  cik: string;
  legal_name: string;
  sic: string | null;
  sic_description: string | null;
  entity_type: string | null;
  state_of_incorporation: string | null;
  fiscal_year_end: string | null;
  exchanges: string[];
  tickers: string[];
  ingestion_method: FundamentalIngestionMethod;
  source_filename: string | null;
  imported_at: string | null;
  received_at: string;
  created_at: string;
  updated_at: string;
}

export interface FundamentalFiling {
  id: number;
  asset_id: number;
  provider: string;
  accession_number: string;
  form: string;
  filing_date: string;
  report_date: string | null;
  acceptance_datetime: string | null;
  primary_document: string | null;
  primary_doc_description: string | null;
  file_number: string | null;
  film_number: string | null;
  items: string | null;
  is_inline_xbrl: boolean;
  is_xbrl: boolean;
  is_amendment: boolean;
  amended_form: string | null;
  filing_url: string | null;
  ingestion_method: FundamentalIngestionMethod;
  source_filename: string | null;
  imported_at: string | null;
  received_at: string;
  created_at: string;
}

export interface FundamentalProvenanceFact {
  id: number;
  value: string;
  unit: string;
  taxonomy: string;
  concept: string;
  period_start: string | null;
  period_end: string;
  period_type: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
  frame: string | null;
  filed_at: string;
  form: string;
  accession_number: string;
  acceptance_datetime: string | null;
  filing_url: string | null;
  is_amendment: boolean;
  ingestion_method: FundamentalIngestionMethod;
  source_filename: string | null;
}

export interface FundamentalCalculationComponent {
  id: number;
  identity: string;
  metric: string;
  value: string;
  unit: string;
  start: string | null;
  end: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
  form: string;
  accession_number: string;
  filed: string;
  frame: string | null;
  is_amendment: boolean;
  is_repeated_comparative: boolean;
  source_filename: string | null;
  ingestion_method: FundamentalIngestionMethod;
}

export interface FundamentalMetricPoint {
  metric: string;
  value: string | null;
  unit: string | null;
  period_start: string | null;
  period_end: string;
  period_type: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
  frame: string | null;
  selected_fact: FundamentalProvenanceFact | null;
  alternative_facts: FundamentalProvenanceFact[];
  source_facts: FundamentalProvenanceFact[];
  calculation_components: FundamentalCalculationComponent[];
  selection_reason: string;
  is_repeated_comparative: boolean;
  is_restated: boolean;
  has_conflict: boolean;
  warnings: string[];
  calculation: string | null;
  derived: boolean;
  derivation_method: string | null;
  confidence: string | null;
  status: FundamentalMetricStatus;
}

export interface FundamentalPeriod {
  period_start: string;
  period_end: string;
  period_type: string;
  fiscal_year: number | null;
  fiscal_period: string | null;
  frame: string | null;
}

export interface FundamentalMarketPrice {
  value: string;
  provider: string;
  event_time: string;
  received_at: string;
  is_stale: boolean;
}

export interface FundamentalCompleteness {
  status: "complete" | "partial" | "insufficient_data" | string;
  available_metrics: number;
  expected_metrics: number;
  ratio: string;
  missing_metrics: string[];
}

export interface FundamentalMetricsView {
  symbol: string;
  provider: string;
  period_type: FundamentalPeriodType;
  as_of: string;
  periods: FundamentalPeriod[];
  metrics: Record<string, FundamentalMetricPoint[]>;
  market_price: FundamentalMarketPrice | null;
  warnings: string[];
  completeness: FundamentalCompleteness;
}

export type FundamentalFactProvenance = FundamentalProvenanceFact;
export type FundamentalMetricsResponse = FundamentalMetricsView;

export interface PoliticalEvent {
  date: string;
  time: string;
  title: string;
  region: string;
  impact: "High" | "Medium" | "Low";
  assets: string[];
  summary: string;
}
