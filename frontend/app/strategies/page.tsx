"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, StrategyConfig, StrategyInfo } from "@/lib/api";

export default function StrategiesPage() {
  const [builtin, setBuiltin] = useState<StrategyInfo[]>([]);
  const [custom, setCustom] = useState<StrategyConfig[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    const [all, configs] = await Promise.all([
      api.getStrategies(),
      api.getStrategyConfigs(),
    ]);
    setBuiltin(all.filter((s) => s.source !== "custom"));
    setCustom(configs);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, []);

  async function removeConfig(id?: string | null) {
    if (!id) return;
    if (!confirm("Delete this strategy?")) return;
    await api.deleteStrategyConfig(id);
    await refresh();
  }

  return (
    <div className="stack">
      <div className="creator-head">
        <div>
          <h1>Strategies</h1>
          <p className="muted">
            Build custom strategies with pandas-ta indicators, or use the built-ins.
          </p>
        </div>
        <div className="row" style={{ flex: "0 0 auto" }}>
          <Link href="/strategies/new" className="button-link">
            + Create strategy
          </Link>
          <Link href="/strategies/new?import=pine" className="secondary-link">
            Import Pine Script
          </Link>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section className="stack">
        <h2>Your strategies</h2>
        {custom.length === 0 ? (
          <p className="muted">No custom strategies yet. Create one to get started.</p>
        ) : (
          <div className="grid">
            {custom.map((strategy) => (
              <article key={strategy.id || strategy.name} className="card">
                <h2>{strategy.name}</h2>
                <p>
                  {strategy.yahoo_ticker}
                  {strategy.broker_ticker ? ` · ${strategy.broker_ticker}` : ""}
                </p>
                <p className="muted" style={{ marginTop: 10 }}>
                  {strategy.interval} · {strategy.period} · {strategy.direction}
                </p>
                <div className="card-actions">
                  <Link href={`/strategies/${strategy.id}`} className="button-link">
                    Modify
                  </Link>
                  <Link
                    href={`/backtest?strategy=${strategy.id}`}
                    className="secondary-link"
                  >
                    Backtest
                  </Link>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => removeConfig(strategy.id)}
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="stack">
        <h2>Built-in examples</h2>
        <div className="grid">
          {builtin.map((strategy) => (
            <article key={strategy.id} className="card">
              <h2>{strategy.name}</h2>
              <p>{strategy.description}</p>
              <p className="muted" style={{ marginTop: 12 }}>
                id: <code>{strategy.id}</code>
              </p>
              <div className="card-actions">
                <Link
                  href={`/backtest?strategy=${strategy.id}`}
                  className="button-link"
                >
                  Backtest
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
