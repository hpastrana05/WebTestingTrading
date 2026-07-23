"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, BacktestResult, StrategyInfo } from "@/lib/api";
import { DATA_INTERVALS } from "@/lib/intervals";
import { DATA_PERIODS } from "@/lib/periods";

type EquityPoint = { date: string; equity: number; buy_hold: number; price: number };

function formatMoney(value: number) {
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function EquitySpark({ points }: { points: EquityPoint[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const chart = useMemo(() => {
    if (!points.length) {
      return { strategyPath: "", buyHoldPath: "", min: 0, max: 1, span: 1 };
    }
    const strategy = points.map((p) => p.equity);
    const buyHold = points.map((p) => p.buy_hold);
    const all = [...strategy, ...buyHold];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const span = max - min || 1;

    const toPath = (values: number[]) =>
      values
        .map((value, index) => {
          const x = (index / Math.max(values.length - 1, 1)) * 100;
          const y = 100 - ((value - min) / span) * 100;
          return `${index === 0 ? "M" : "L"} ${x},${y}`;
        })
        .join(" ");

    return {
      strategyPath: toPath(strategy),
      buyHoldPath: toPath(buyHold),
      min,
      max,
      span,
    };
  }, [points]);

  if (!points.length) return null;

  const start = points[0];
  const end = points[points.length - 1];
  const active = hoverIndex != null ? points[hoverIndex] : null;
  const last = points.length - 1;

  function yOf(value: number) {
    return 100 - ((value - chart.min) / chart.span) * 100;
  }

  function onMove(event: MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / Math.max(rect.width, 1);
    const index = Math.round(ratio * last);
    setHoverIndex(Math.max(0, Math.min(last, index)));
  }

  const hoverX = hoverIndex != null ? (hoverIndex / Math.max(last, 1)) * 100 : 0;

  return (
    <div className="spark-wrap">
      <div className="spark-meta">
        <span>
          Started <strong>{start.date}</strong>
        </span>
        <span>
          Ended <strong>{end.date}</strong>
        </span>
        <span>
          Bars <strong>{points.length}</strong>
        </span>
      </div>

      <div
        className="spark-stage"
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        <svg className="spark" viewBox="0 0 100 100" preserveAspectRatio="none">
          <path
            d={chart.buyHoldPath}
            fill="none"
            stroke="#7a8794"
            strokeWidth="1.5"
            strokeDasharray="3 2"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={chart.strategyPath}
            fill="none"
            stroke="#3d9b6e"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
          {active && hoverIndex != null && (
            <>
              <line
                x1={hoverX}
                y1={0}
                x2={hoverX}
                y2={100}
                stroke="rgba(255,255,255,0.28)"
                strokeWidth="0.4"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={hoverX}
                cy={yOf(active.equity)}
                r="1.2"
                fill="#3d9b6e"
                vectorEffect="non-scaling-stroke"
              />
              <circle
                cx={hoverX}
                cy={yOf(active.buy_hold)}
                r="1.2"
                fill="#7a8794"
                vectorEffect="non-scaling-stroke"
              />
            </>
          )}
        </svg>

        {active && hoverIndex != null && (
          <div
            className="spark-tooltip"
            style={{
              left: `${Math.min(Math.max(hoverX, 8), 92)}%`,
            }}
          >
            <div className="spark-tooltip-date">{active.date}</div>
            <div>
              Price <strong>{formatMoney(active.price)}</strong>
            </div>
            <div>
              <span className="legend-strategy">Strategy</span> {formatMoney(active.equity)}
            </div>
            <div>
              <span className="legend-buyhold">Buy &amp; hold</span>{" "}
              {formatMoney(active.buy_hold)}
            </div>
          </div>
        )}
      </div>

      <div className="spark-legend">
        <span className="legend-strategy">Strategy</span>
        <span className="legend-buyhold">Buy &amp; hold</span>
        <span className="muted">Hover the chart for values at each bar</span>
      </div>
    </div>
  );
}

export default function BacktestClient() {
  const searchParams = useSearchParams();
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState("1y");
  const [interval, setInterval] = useState("1d");
  const [initialCash, setInitialCash] = useState(10000);
  const [positionSizePct, setPositionSizePct] = useState(100);
  const [commissionPct, setCommissionPct] = useState(0.001);
  const [riskPercent, setRiskPercent] = useState(2);
  const [slippage, setSlippage] = useState(0);
  const [fillOn, setFillOn] = useState<"next_open" | "close">("next_open");
  const [parameters, setParameters] = useState<Record<string, number>>({});
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const preferred = searchParams.get("strategy") || "";
    api.getStrategies().then((items) => {
      setStrategies(items);
      const initial = items.find((s) => s.id === preferred) || items[0];
      if (initial) {
        setStrategyId(initial.id);
        const defaults: Record<string, number> = {};
        Object.entries(initial.parameters).forEach(([key, meta]) => {
          defaults[key] = meta.default;
        });
        setParameters(defaults);
      }
    });
  }, [searchParams]);

  useEffect(() => {
    const selected = strategies.find((s) => s.id === strategyId);
    if (!selected) return;
    const defaults: Record<string, number> = {};
    Object.entries(selected.parameters).forEach(([key, meta]) => {
      defaults[key] = meta.default;
    });
    setParameters(defaults);

    if (selected.source === "custom") {
      api.getStrategyConfig(selected.id).then((cfg) => {
        setSymbol(cfg.yahoo_ticker);
        setPeriod(cfg.period);
        setInterval(cfg.interval);
      });
    }
  }, [strategyId, strategies]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await api.runBacktest({
        strategy_id: strategyId,
        symbol,
        period,
        interval,
        parameters,
        initial_cash: initialCash,
        position_size_pct: positionSizePct,
        commission_pct: commissionPct,
        risk_percent: riskPercent,
        slippage,
        fill_on: fillOn,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setLoading(false);
    }
  }

  const selected = strategies.find((s) => s.id === strategyId);
  const isCustom = selected?.source === "custom";

  return (
    <div className="stack">
      <div>
        <h1>Backtest</h1>
        <p className="muted">
          TradingView-like simulation: next-bar fills, intrabar SL/TP, optional risk-% sizing.
        </p>
      </div>

      <form className="panel stack" onSubmit={onSubmit}>
        <div className="row">
          <label>
            Strategy
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.source === "custom" ? `★ ${s.name}` : s.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Symbol
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          </label>
          <label>
            Period
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              {DATA_PERIODS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Interval
            <select value={interval} onChange={(e) => setInterval(e.target.value)}>
              {DATA_INTERVALS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="row">
          <label>
            Initial cash
            <input
              type="number"
              value={initialCash}
              onChange={(e) => setInitialCash(Number(e.target.value))}
            />
          </label>
          <label>
            Risk % / trade
            <input
              type="number"
              min={0}
              step={0.5}
              value={riskPercent}
              onChange={(e) => setRiskPercent(Number(e.target.value))}
              title="TradingView-style: size from equity×risk% / SL distance. 0 = use Position size % instead"
            />
          </label>
          <label>
            Position size %
            <input
              type="number"
              min={1}
              max={100}
              value={positionSizePct}
              onChange={(e) => setPositionSizePct(Number(e.target.value))}
              title="Used only when Risk % is 0"
            />
          </label>
          <label>
            Commission % / trade
            <input
              type="number"
              min={0}
              step={0.001}
              value={commissionPct}
              onChange={(e) => setCommissionPct(Number(e.target.value))}
              title="Enter percent points: 0.001 = 0.001%, 10 = 10%"
              placeholder="0.001"
            />
          </label>
        </div>

        <div className="row">
          <label>
            Slippage (price)
            <input
              type="number"
              min={0}
              step={0.01}
              value={slippage}
              onChange={(e) => setSlippage(Number(e.target.value))}
              title="Absolute price units. TV slippage=2 ticks → e.g. 0.02 for $0.01 tick stocks"
            />
          </label>
          <label>
            Fill orders on
            <select
              value={fillOn}
              onChange={(e) => setFillOn(e.target.value as "next_open" | "close")}
            >
              <option value="next_open">Next bar open (TV default)</option>
              <option value="close">Signal bar close</option>
            </select>
          </label>
        </div>

        {!isCustom && selected && Object.keys(selected.parameters).length > 0 && (
          <div className="row">
            {Object.entries(selected.parameters).map(([key, meta]) => (
              <label key={key}>
                {key}
                <input
                  type="number"
                  value={parameters[key] ?? meta.default}
                  min={meta.min}
                  max={meta.max}
                  step={meta.step ?? 1}
                  onChange={(e) =>
                    setParameters((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                  }
                />
              </label>
            ))}
          </div>
        )}

        {isCustom && (
          <p className="muted">
            Custom strategies use the entry/exit rules (including TP/SL) and direction
            saved in the Strategy Creator.
          </p>
        )}

        <button type="submit" disabled={loading || !strategyId}>
          {loading ? "Running…" : "Run backtest"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <section className="panel stack">
          <div className="metrics">
            <div className="metric">
              Return
              <strong className={result.total_return_pct >= 0 ? "positive" : "negative"}>
                {result.total_return_pct.toFixed(2)}%
              </strong>
            </div>
            <div className="metric">
              Buy &amp; hold
              <strong className={result.buy_hold_return_pct >= 0 ? "positive" : "negative"}>
                {result.buy_hold_return_pct.toFixed(2)}%
              </strong>
            </div>
            <div className="metric">
              Max DD
              <strong className="negative">{result.max_drawdown_pct.toFixed(2)}%</strong>
            </div>
            <div className="metric">
              Final equity
              <strong>${result.final_equity.toLocaleString()}</strong>
            </div>
            <div className="metric">
              Direction
              <strong>{result.direction}</strong>
            </div>
            <div className="metric">
              Trades
              <strong>{result.num_trades}</strong>
            </div>
          </div>

          <EquitySpark points={result.equity_curve} />

          <div>
            <h2>Trades</h2>
            <table>
              <thead>
                <tr>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>Side</th>
                  <th>Exit type</th>
                  <th>Entry price</th>
                  <th>Exit price</th>
                  <th>Shares</th>
                  <th>PnL</th>
                  <th>PnL %</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade, index) => (
                  <tr key={`${trade.entry_date}-${trade.exit_date}-${index}`}>
                    <td>{trade.entry_date}</td>
                    <td>{trade.exit_date}</td>
                    <td>{trade.side}</td>
                    <td>{trade.exit_reason}</td>
                    <td>{trade.entry_price.toFixed(2)}</td>
                    <td>{trade.exit_price.toFixed(2)}</td>
                    <td>{trade.shares.toFixed(4)}</td>
                    <td className={trade.pnl >= 0 ? "positive" : "negative"}>
                      {trade.pnl.toFixed(2)}
                    </td>
                    <td className={trade.pnl_pct >= 0 ? "positive" : "negative"}>
                      {trade.pnl_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
