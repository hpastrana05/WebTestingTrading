"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, StrategyInfo, TuningResult } from "@/lib/api";
import { DATA_INTERVALS } from "@/lib/intervals";
import { DATA_PERIODS } from "@/lib/periods";

function suggestGrid(
  parameters: StrategyInfo["parameters"]
): Record<string, number[]> {
  const grid: Record<string, number[]> = {};
  for (const [name, meta] of Object.entries(parameters || {})) {
    const d = Number(meta.default);
    const lo = meta.min ?? d;
    const hi = meta.max ?? d;
    const step = meta.step ?? (meta.type === "int" ? 1 : 0.1);
    // Default: only fan out exits / scales; leave lengths as single values
    // so custom grids stay small. Expand arrays manually to search more.
    const fanOut = /atr_mult|rr_ratio|scale|sl_pct|tp_pct/.test(name);
    if (!fanOut) {
      grid[name] = [meta.type === "int" ? Math.round(d) : d];
      continue;
    }
    const spread = 2;
    if (meta.type === "int") {
      const vals = new Set<number>([
        Math.round(d),
        Math.round(Math.max(lo, d - spread * step)),
        Math.round(Math.min(hi, d + spread * step)),
      ]);
      grid[name] = [...vals].filter((v) => v >= lo && v <= hi).sort((a, b) => a - b);
    } else {
      const vals = new Set<number>([
        d,
        Number(Math.max(lo, d - spread * step).toFixed(4)),
        Number(Math.min(hi, d + spread * step).toFixed(4)),
      ]);
      grid[name] = [...vals].filter((v) => v >= lo && v <= hi).sort((a, b) => a - b);
    }
    if (!grid[name].length) grid[name] = [d];
  }
  return grid;
}

function countCombos(grid: Record<string, number[]>): number {
  const keys = Object.keys(grid);
  if (!keys.length) return 0;
  return keys.reduce((acc, k) => acc * Math.max(grid[k].length, 1), 1);
}

function formatParamValue(value: unknown): string {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return String(value);
    if (Number.isInteger(value)) return String(value);
    return String(Number(value.toFixed(4)));
  }
  return String(value);
}

function ParamChips({
  parameters,
  highlight,
}: {
  parameters: Record<string, unknown>;
  highlight?: Set<string>;
}) {
  const entries = Object.entries(parameters || {});
  if (!entries.length) {
    return <span className="muted">—</span>;
  }
  return (
    <div className="param-chips">
      {entries.map(([key, value]) => (
        <span
          key={key}
          className={`param-chip${highlight?.has(key) ? " is-varied" : ""}`}
          title={key}
        >
          <span className="param-chip-key">{key}</span>
          <span className="param-chip-val">{formatParamValue(value)}</span>
        </span>
      ))}
    </div>
  );
}

function variedKeys(trials: TuningResult["trials"]): Set<string> {
  if (!trials.length) return new Set();
  const keys = Object.keys(trials[0].parameters || {});
  const varied = new Set<string>();
  for (const key of keys) {
    const first = formatParamValue(trials[0].parameters[key]);
    if (trials.some((t) => formatParamValue(t.parameters[key]) !== first)) {
      varied.add(key);
    }
  }
  return varied;
}

function pickParams(
  parameters: Record<string, unknown>,
  keys: Set<string>
): Record<string, unknown> {
  if (!keys.size) return parameters;
  const picked: Record<string, unknown> = {};
  for (const key of keys) {
    if (key in parameters) picked[key] = parameters[key];
  }
  // If nothing varied (single trial / single-value grid), show everything
  return Object.keys(picked).length ? picked : parameters;
}

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

  const selected = useMemo(
    () => strategies.find((s) => s.id === strategyId),
    [strategies, strategyId]
  );

  const comboHint = useMemo(() => {
    try {
      const grid = JSON.parse(gridText) as Record<string, number[]>;
      const n = countCombos(grid);
      return n > 0 ? `${n} combination${n === 1 ? "" : "s"}` : "";
    } catch {
      return "";
    }
  }, [gridText]);

  const variedParamKeys = useMemo(
    () => (result ? variedKeys(result.trials) : new Set<string>()),
    [result]
  );

  useEffect(() => {
    api.getStrategies().then((items) => {
      setStrategies(items);
      if (items[0]) setStrategyId(items[0].id);
    });
  }, []);

  useEffect(() => {
    if (!strategyId || !selected) return;

    if (strategyId === "rsi") {
      setGridText(
        '{\n  "period": [10, 14],\n  "oversold": [25, 30],\n  "overbought": [70, 75]\n}'
      );
      return;
    }
    if (strategyId === "sma_crossover") {
      setGridText('{\n  "fast": [5, 10, 15],\n  "slow": [20, 30, 40]\n}');
      return;
    }
    if (strategyId === "vwap_momentum") {
      setGridText(
        '{\n  "ema_length": [20],\n  "atr_length": [14],\n  "atr_mult": [1.0, 1.1, 1.2],\n  "rr_ratio": [2.0, 2.3, 2.5],\n  "impulse_lookback": [15],\n  "impulse_mult": [1.1]\n}'
      );
      setInterval("5m");
      setPeriod("5d");
      setSymbol("QQQ");
      setCommissionPct(0.001);
      setRiskPercent(2);
      setFillOn("next_open");
      return;
    }
    if (strategyId === "oro_swing_adaptive") {
      setGridText(
        '{\n  "ema_fast": [50],\n  "ema_slow": [200],\n  "rsi_period": [14],\n  "atr_length": [20],\n  "rr_ratio": [2.5, 3.0, 3.5],\n  "atr_mult_normal": [2.3, 2.5, 2.7],\n  "atr_mult_strict": [3.0],\n  "loss_streak": [2],\n  "rsi_long_normal": [45],\n  "rsi_long_strict": [50],\n  "rsi_short_normal": [55],\n  "rsi_short_strict": [50]\n}'
      );
      setInterval("1d");
      setPeriod("2y");
      setSymbol("GC=F");
      setCommissionPct(0.002);
      setRiskPercent(2);
      setSlippage(2);
      setFillOn("next_open");
      return;
    }

    // Custom / hand-made strategies: load market defaults + auto grid from rule params
    if (selected.source === "custom") {
      api
        .getStrategyConfig(strategyId)
        .then((cfg) => {
          if (cfg.yahoo_ticker) setSymbol(cfg.yahoo_ticker);
          if (cfg.interval) setInterval(cfg.interval);
          if (cfg.period) setPeriod(cfg.period);
        })
        .catch(() => {
          /* keep current market fields */
        });

      const params = selected.parameters || {};
      if (!Object.keys(params).length) {
        setGridText("{\n}");
        return;
      }
      const grid = suggestGrid(params);
      setGridText(JSON.stringify(grid, null, 2));
    }
  }, [strategyId, selected]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const param_grid = JSON.parse(gridText);
      if (!param_grid || !Object.keys(param_grid).length) {
        throw new Error(
          selected?.source === "custom"
            ? "This custom strategy has no numeric rule parameters to tune (indicator lengths, ATR/R:R, scales, TP/SL %). Edit the strategy first."
            : "param_grid must include at least one parameter list"
        );
      }
      const combos = countCombos(param_grid);
      if (combos > 200) {
        throw new Error(
          `Grid has ${combos} combinations (max 200). Reduce some arrays to fewer values.`
        );
      }
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
          backtest. Custom strategies tune indicator lengths, scales, and TP/SL / ATR fields
          from the Strategy Creator.
        </p>
      </div>

      <form className="panel stack" onSubmit={onSubmit}>
        <div className="row">
          <label>
            Strategy
            <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.source === "custom" ? `${s.name} (custom)` : s.name}
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
          {comboHint ? <span className="muted"> · {comboHint}</span> : null}
          <textarea value={gridText} onChange={(e) => setGridText(e.target.value)} rows={12} />
        </label>
        {selected?.source === "custom" && (
          <p className="muted">
            Keys like <code>entry0_R_length</code>, <code>exit0_atr_mult</code>,{" "}
            <code>entry1_scale</code> come from your rule tree. Edit the arrays to search more
            (or fewer) values.
          </p>
        )}

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
              Trials
              <strong>{result.trials.length}</strong>
            </div>
          </div>

          <div className="stack">
            <h2>Best parameters</h2>
            <ParamChips
              parameters={pickParams(result.best_parameters, variedParamKeys)}
              highlight={variedParamKeys}
            />
            {variedParamKeys.size > 0 && (
              <p className="muted">
                Highlighted chips are the values that changed across the grid search.
              </p>
            )}
          </div>

          <div>
            <h2>All trials</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Parameters</th>
                    <th>Return %</th>
                    <th>Final equity</th>
                    <th>Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trials.map((trial, index) => (
                    <tr key={index}>
                      <td>{index + 1}</td>
                      <td>
                        <ParamChips
                          parameters={pickParams(trial.parameters, variedParamKeys)}
                          highlight={variedParamKeys}
                        />
                      </td>
                      <td
                        className={
                          trial.total_return_pct >= 0 ? "positive" : "negative"
                        }
                      >
                        {trial.total_return_pct.toFixed(2)}
                      </td>
                      <td>{trial.final_equity.toLocaleString()}</td>
                      <td>{trial.num_trades}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
