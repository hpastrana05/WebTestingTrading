"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, BacktestResult, StrategyInfo } from "@/lib/api";

function EquitySpark({ points }: { points: { equity: number }[] }) {
  const path = useMemo(() => {
    if (!points.length) return "";
    const values = points.map((p) => p.equity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    return values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * 100;
        const y = 100 - ((value - min) / span) * 100;
        return `${index === 0 ? "M" : "L"} ${x},${y}`;
      })
      .join(" ");
  }, [points]);

  return (
    <svg className="spark" viewBox="0 0 100 100" preserveAspectRatio="none">
      <path
        d={path}
        fill="none"
        stroke="#3d9b6e"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default function BacktestClient() {
  const searchParams = useSearchParams();
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState("1y");
  const [initialCash, setInitialCash] = useState(10000);
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
        parameters,
        initial_cash: initialCash,
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
        <p className="muted">Run a long-only historical simulation.</p>
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
              {["3mo", "6mo", "1y", "2y", "5y"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label>
            Initial cash
            <input
              type="number"
              value={initialCash}
              onChange={(e) => setInitialCash(Number(e.target.value))}
            />
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
            Custom strategies use the entry/exit rules saved in the Strategy Creator.
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
              Final equity
              <strong>${result.final_equity.toLocaleString()}</strong>
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
                  <th>Date</th>
                  <th>Side</th>
                  <th>Price</th>
                  <th>Shares</th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((trade, index) => (
                  <tr key={`${trade.date}-${trade.side}-${index}`}>
                    <td>{trade.date}</td>
                    <td>{trade.side}</td>
                    <td>{trade.price.toFixed(2)}</td>
                    <td>{trade.shares.toFixed(4)}</td>
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
