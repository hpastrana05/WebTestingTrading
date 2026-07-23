const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ")
          : `Request failed (${res.status})`;
    throw new Error(message);
  }

  return res.json();
}

export type StrategyInfo = {
  id: string;
  name: string;
  description: string;
  parameters: Record<
    string,
    { type: string; default: number; min?: number; max?: number; step?: number }
  >;
  source?: "builtin" | "custom";
};

export type IndicatorParam = {
  name: string;
  type: string;
  default: number;
  min?: number;
  max?: number;
  step?: number;
};

export type IndicatorInfo = {
  id: string;
  label: string;
  category: string;
  inputs: string[];
  params: IndicatorParam[];
  outputs: { id: string; label: string }[];
};

export type IndicatorCatalog = {
  indicators: IndicatorInfo[];
  operators: { id: string; label: string }[];
  price_fields: { id: string; label: string }[];
};

export type Operand = {
  kind: "price" | "indicator" | "value";
  field?: string | null;
  indicator?: string | null;
  params?: Record<string, number>;
  output?: string | null;
  value?: number | null;
};

export type RuleNode = {
  type: "condition" | "group";
  left?: Operand | null;
  operator?: string | null;
  right?: Operand | null;
  logic?: "all" | "any" | null;
  children?: RuleNode[];
};

export type StrategyConfig = {
  id?: string | null;
  name: string;
  broker_ticker: string;
  yahoo_ticker: string;
  interval: string;
  period: string;
  action: "buy";
  entry: RuleNode;
  exit: RuleNode;
};

export type BacktestResult = {
  strategy_id: string;
  symbol: string;
  parameters: Record<string, number>;
  initial_cash: number;
  final_equity: number;
  total_return_pct: number;
  num_trades: number;
  trades: { date: string; side: string; price: number; shares: number }[];
  equity_curve: { date: string; equity: number }[];
};

export type TuningResult = {
  strategy_id: string;
  symbol: string;
  metric: string;
  best_parameters: Record<string, number>;
  best_score: number;
  trials: {
    parameters: Record<string, number>;
    total_return_pct: number;
    final_equity: number;
    num_trades: number;
  }[];
};

export type AlertRule = {
  id?: string;
  name: string;
  strategy_id: string;
  symbol: string;
  parameters: Record<string, number>;
  enabled: boolean;
  notify_on: string[];
};

export const api = {
  getStrategies: () => request<StrategyInfo[]>("/api/strategies"),
  getIndicators: () => request<IndicatorCatalog>("/api/indicators"),
  getStrategyConfigs: () => request<StrategyConfig[]>("/api/strategies/configs/all"),
  getStrategyConfig: (id: string) =>
    request<StrategyConfig>(`/api/strategies/configs/${id}`),
  createStrategyConfig: (body: StrategyConfig) =>
    request<StrategyConfig>("/api/strategies/configs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateStrategyConfig: (id: string, body: Partial<StrategyConfig>) =>
    request<StrategyConfig>(`/api/strategies/configs/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteStrategyConfig: (id: string) =>
    request<{ ok: boolean }>(`/api/strategies/configs/${id}`, { method: "DELETE" }),
  runBacktest: (body: unknown) =>
    request<BacktestResult>("/api/backtest", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  runTuning: (body: unknown) =>
    request<TuningResult>("/api/tuning", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sendAlert: (message: string) =>
    request<{ ok: boolean; message_id?: number }>("/api/alerts/send", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  checkAlerts: () =>
    request<{ results: unknown[] }>("/api/alerts/check", { method: "POST" }),
  getAlertRules: () => request<AlertRule[]>("/api/alerts/rules"),
  createAlertRule: (rule: AlertRule) =>
    request<AlertRule>("/api/alerts/rules", {
      method: "POST",
      body: JSON.stringify(rule),
    }),
  deleteAlertRule: (id: string) =>
    request<{ ok: boolean }>(`/api/alerts/rules/${id}`, { method: "DELETE" }),
};
