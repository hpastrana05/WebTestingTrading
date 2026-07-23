"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, StrategyInfo, TuningResult } from "@/lib/api";

export default function TuningPage() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState("1y");
  const [gridText, setGridText] = useState('{\n  "fast": [5, 10, 15],\n  "slow": [20, 30, 40]\n}');
  const [result, setResult] = useState<TuningResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getStrategies().then((items) => {
      setStrategies(items);
      if (items[0]) setStrategyId(items[0].id);
    });
  }, []);

  useEffect(() => {
    if (strategyId === "rsi") {
      setGridText('{\n  "period": [10, 14],\n  "oversold": [25, 30],\n  "overbought": [70, 75]\n}');
    } else if (strategyId === "sma_crossover") {
      setGridText('{\n  "fast": [5, 10, 15],\n  "slow": [20, 30, 40]\n}');
    }
  }, [strategyId]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const param_grid = JSON.parse(gridText);
      const data = await api.runTuning({
        strategy_id: strategyId,
        symbol,
        period,
        param_grid,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tuning failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Parameter tuning</h1>
        <p className="muted">Simple grid search over strategy parameters.</p>
      </div>

      <form className="panel stack" onSubmit={onSubmit}>
        <div className="row">
          <label>
            Strategy
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
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
              {["6mo", "1y", "2y"].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label>
          Parameter grid (JSON)
          <textarea value={gridText} onChange={(e) => setGridText(e.target.value)} />
        </label>

        <button type="submit" disabled={loading || !strategyId}>
          {loading ? "Searching…" : "Run tuning"}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {result && (
        <section className="panel stack">
          <div className="metrics">
            <div className="metric">
              Best return
              <strong className={result.best_score >= 0 ? "positive" : "negative"}>
                {result.best_score.toFixed(2)}%
              </strong>
            </div>
            <div className="metric">
              Best params
              <strong style={{ fontSize: "0.95rem" }}>
                {JSON.stringify(result.best_parameters)}
              </strong>
            </div>
            <div className="metric">
              Trials
              <strong>{result.trials.length}</strong>
            </div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Parameters</th>
                <th>Return %</th>
                <th>Final equity</th>
                <th>Trades</th>
              </tr>
            </thead>
            <tbody>
              {result.trials.map((trial, index) => (
                <tr key={index}>
                  <td>
                    <code>{JSON.stringify(trial.parameters)}</code>
                  </td>
                  <td>{trial.total_return_pct.toFixed(2)}</td>
                  <td>{trial.final_equity.toLocaleString()}</td>
                  <td>{trial.num_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
