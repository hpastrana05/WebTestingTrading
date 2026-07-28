// Empty = same-origin /api (Next.js rewrite → backend). Works on LAN / Pi / localhost.
// Set NEXT_PUBLIC_API_URL only if the API is on a different public host.
const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

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
  source?: "builtin" | "custom" | "generated";
  direction?: "long" | "short" | "both";
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
  type: "condition" | "group" | "risk";
  left?: Operand | null;
  operator?: string | null;
  right?: Operand | null;
  right_scale?: number | null;
  logic?: "all" | "any" | null;
  children?: RuleNode[];
  risk?: "stop_loss" | "take_profit" | "structure_atr" | null;
  pct?: number | null;
  atr_length?: number | null;
  atr_mult?: number | null;
  rr_ratio?: number | null;
};

export type StrategyConfig = {
  id?: string | null;
  name: string;
  broker_ticker: string;
  yahoo_ticker: string;
  interval: string;
  period: string;
  direction: "long" | "short" | "both";
  trade_session: string;
  close_session: string;
  timezone: string;
  one_trade_per_day: boolean;
  entry: RuleNode;
  entry_short: RuleNode;
  exit: RuleNode;
};

export type BacktestResult = {
  strategy_id: string;
  symbol: string;
  parameters: Record<string, number>;
  direction: "long" | "short" | "both";
  initial_cash: number;
  final_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  buy_hold_return_pct: number;
  num_trades: number;
  trades: {
    entry_date: string;
    exit_date: string;
    side: string;
    exit_reason: string;
    entry_price: number;
    exit_price: number;
    shares: number;
    pnl: number;
    pnl_pct: number;
  }[];
  equity_curve: { date: string; equity: number; buy_hold: number; price: number }[];
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
  interval: string;
  period: string;
  parameters: Record<string, number>;
  enabled: boolean;
  notify_on: string[];
};

export type TelegramChat = {
  id: string;
  name: string;
  chat_id: string;
  enabled: boolean;
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
  importPine: (code: string) =>
    request<{
      config: StrategyConfig;
      warnings: string[];
      python_code: string;
      python_filename: string;
      strategy_id: string;
      reliability: string;
    }>("/api/strategies/import-pine", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  savePineAsPython: (code: string) =>
    request<{
      id: string;
      name: string;
      filename: string;
      python_code: string;
      warnings: string[];
    }>("/api/strategies/import-pine/save-python", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  deleteGeneratedStrategy: (id: string) =>
    request<{ ok: boolean }>(`/api/strategies/generated/${id}`, { method: "DELETE" }),
  renameGeneratedStrategy: (id: string, name: string) =>
    request<StrategyInfo>(`/api/strategies/generated/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
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
    request<{ results: Array<{ event?: string; ok?: boolean; detail?: string }> }>(
      "/api/alerts/check",
      { method: "POST" }
    ),
  getAlertRules: () => request<AlertRule[]>("/api/alerts/rules"),
  createAlertRule: (rule: AlertRule) =>
    request<AlertRule>("/api/alerts/rules", {
      method: "POST",
      body: JSON.stringify(rule),
    }),
  deleteAlertRule: (id: string) =>
    request<{ ok: boolean }>(`/api/alerts/rules/${id}`, { method: "DELETE" }),

  // Telegram chat targets
  getTelegramChats: () => request<TelegramChat[]>("/api/telegram/chats", { method: "GET" }),
  createTelegramChat: (body: { name: string; chat_id: string }) =>
    request<TelegramChat>("/api/telegram/chats", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateTelegramChat: (
    chatEntryId: string,
    body: Partial<Pick<TelegramChat, "name" | "chat_id" | "enabled">>
  ) =>
    request<TelegramChat>(`/api/telegram/chats/${chatEntryId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteTelegramChat: (chatEntryId: string) =>
    request<{ ok: boolean }>(`/api/telegram/chats/${chatEntryId}`, { method: "DELETE" }),
};
