"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, StrategyInfo, TuningResult } from "@/lib/api";
import { DATA_INTERVALS } from "@/lib/intervals";
import { DATA_PERIODS } from "@/lib/periods";

export default function TuningPage() {
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
    } else if (strategyId === "vwap_momentum") {
      setGridText(
        '{\n  "ema_length": [20],\n  "atr_length": [14],\n  "atr_mult": [1.0, 1.1, 1.2],\n  "rr_ratio": [2.0, 2.3, 2.5],\n  "impulse_lookback": [15],\n  "impulse_mult": [1.1]\n}'
      );
      setInterval("5m");
      setPeriod("5d");
      setSymbol("QQQ");
      setCommissionPct(0.001);
      setRiskPercent(2);
      setFillOn("next_open");
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
        interval,
        initial_cash: initialCash,
        position_size_pct: positionSizePct,
        commission_pct: commissionPct,
        risk_percent: riskPercent,
        slippage,
        fill_on: fillOn,
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
        <p className="muted">
          Grid search over strategy parameters using the same market and cost settings as
          backtest.
        </p>
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
