"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, StrategyConfig, StrategyInfo } from "@/lib/api";

function isGenerated(s: StrategyInfo): boolean {
  return s.source === "generated" || s.id.startsWith("gen_");
}

export default function StrategiesPage() {
  const [builtin, setBuiltin] = useState<StrategyInfo[]>([]);
  const [generated, setGenerated] = useState<StrategyInfo[]>([]);
  const [custom, setCustom] = useState<StrategyConfig[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  async function refresh() {
    const [all, configs] = await Promise.all([
      api.getStrategies(),
      api.getStrategyConfigs(),
    ]);
    setGenerated(all.filter(isGenerated));
    setBuiltin(all.filter((s) => !isGenerated(s) && s.source !== "custom"));
    setCustom(configs);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, []);

  async function removeConfig(id?: string | null) {
    if (!id) return;
    if (!confirm("Delete this strategy?")) return;
    setError("");
    setStatus("");
    try {
      await api.deleteStrategyConfig(id);
      setStatus("Strategy deleted.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function removeGenerated(id: string) {
    if (!confirm(`Delete Python strategy “${id}”? This cannot be undone.`)) return;
    setError("");
    setStatus("");
    try {
      await api.deleteGeneratedStrategy(id);
      setStatus(`Deleted Python strategy ${id}.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function renameGenerated(strategy: StrategyInfo) {
    const current = strategy.name.replace(/^\[Python\]\s*/i, "");
    const next = window.prompt("New name for this Python strategy:", current);
    if (next == null) return;
    const trimmed = next.trim();
    if (!trimmed) {
      setError("Name cannot be empty.");
      return;
    }
    setError("");
    setStatus("");
    try {
      const updated = await api.renameGeneratedStrategy(strategy.id, trimmed);
      setStatus(`Renamed to “${updated.name}”.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rename failed");
    }
  }

  function pythonLabel(name: string): string {
    const clean = name.replace(/^\[Python\]\s*/i, "").trim();
    return `[Python] ${clean || "Strategy"}`;
  }

  return (
    <div className="stack">
      <div className="creator-head">
        <div>
          <h1>Strategies</h1>
          <p className="muted">
            Build custom strategies, import Pine (Creator and/or Python), or use built-ins.
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
      {status && <div className="success">{status}</div>}

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
        <h2>Generated from Pine (Python)</h2>
        {generated.length === 0 ? (
          <p className="muted">
            No generated Python strategies yet. Use{" "}
            <Link href="/strategies/new?import=pine">Import Pine Script</Link> →{" "}
            <strong>Save as Python strategy</strong>.
          </p>
        ) : (
          <div className="grid">
            {generated.map((strategy) => (
              <article key={strategy.id} className="card">
                <h2>{pythonLabel(strategy.name)}</h2>
                <p>{strategy.description}</p>
                <p className="muted" style={{ marginTop: 12 }}>
                  Python · id: <code>{strategy.id}</code>
                </p>
                <div className="card-actions">
                  <Link
                    href={`/backtest?strategy=${strategy.id}`}
                    className="button-link"
                  >
                    Backtest
                  </Link>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => renameGenerated(strategy)}
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => removeGenerated(strategy.id)}
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
