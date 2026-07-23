"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import RuleBuilder, { emptyGroup } from "@/components/RuleBuilder";
import {
  api,
  IndicatorCatalog,
  RuleNode,
  StrategyConfig,
} from "@/lib/api";

type Props = {
  strategyId?: string;
};

const defaultConfig = (): Omit<StrategyConfig, "id"> => ({
  name: "",
  broker_ticker: "",
  yahoo_ticker: "AAPL",
  interval: "1d",
  period: "1y",
  action: "buy",
  entry: emptyGroup("all"),
  exit: emptyGroup("any"),
});

export default function StrategyCreator({ strategyId }: Props) {
  const router = useRouter();
  const [catalog, setCatalog] = useState<IndicatorCatalog | null>(null);
  const [config, setConfig] = useState(defaultConfig());
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .getIndicators()
      .then(setCatalog)
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!strategyId) return;
    api
      .getStrategyConfig(strategyId)
      .then((saved) => {
        setConfig({
          name: saved.name,
          broker_ticker: saved.broker_ticker,
          yahoo_ticker: saved.yahoo_ticker,
          interval: saved.interval,
          period: saved.period,
          action: saved.action,
          entry: saved.entry,
          exit: saved.exit,
        });
      })
      .catch((err: Error) => setError(err.message));
  }, [strategyId]);

  function setEntry(entry: RuleNode) {
    setConfig((prev) => ({ ...prev, entry }));
  }

  function setExit(exit: RuleNode) {
    setConfig((prev) => ({ ...prev, exit }));
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setStatus("");
    try {
      if (!config.name.trim()) {
        throw new Error("Strategy name is required");
      }
      if (!(config.entry.children && config.entry.children.length)) {
        throw new Error("Add at least one entry signal");
      }
      if (!(config.exit.children && config.exit.children.length)) {
        throw new Error("Add at least one exit signal");
      }

      if (strategyId) {
        await api.updateStrategyConfig(strategyId, config);
        setStatus("Strategy updated.");
      } else {
        const created = await api.createStrategyConfig(config);
        setStatus("Strategy saved.");
        router.push(`/strategies/${created.id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setLoading(false);
    }
  }

  if (!catalog) {
    return (
      <div className="stack">
        <h1>Strategy Creator</h1>
        <p className="muted">{error || "Loading indicator catalog…"}</p>
      </div>
    );
  }

  return (
    <form className="stack creator" onSubmit={onSave}>
      <div className="creator-head">
        <div>
          <h1>Strategy Creator</h1>
          <p className="muted">
            Configure entry/exit signal logic. Indicators come from{" "}
            <code>pandas-ta</code>.
          </p>
        </div>
        <Link className="secondary-link" href="/strategies">
          ← Back to strategies
        </Link>
      </div>

      <section className="panel stack">
        <h2>Strategy Parameters</h2>
        <div className="row">
          <label>
            Strategy Name
            <input
              value={config.name}
              onChange={(e) => setConfig({ ...config, name: e.target.value })}
              placeholder="EMA Crossover with RSI Filter"
              required
            />
          </label>
          <label>
            Broker Ticker (API)
            <input
              value={config.broker_ticker}
              onChange={(e) => setConfig({ ...config, broker_ticker: e.target.value })}
              placeholder="AAPL_US_EQ"
            />
          </label>
          <label>
            Yahoo Ticker (DATA)
            <input
              value={config.yahoo_ticker}
              onChange={(e) =>
                setConfig({ ...config, yahoo_ticker: e.target.value.toUpperCase() })
              }
              placeholder="AAPL"
              required
            />
          </label>
        </div>
        <div className="row">
          <label>
            Data Interval
            <select
              value={config.interval}
              onChange={(e) => setConfig({ ...config, interval: e.target.value })}
            >
              <option value="1d">1 Day</option>
              <option value="1h">1 Hour</option>
              <option value="15m">15 Minutes</option>
              <option value="5m">5 Minutes</option>
            </select>
          </label>
          <label>
            Default Data Period
            <select
              value={config.period}
              onChange={(e) => setConfig({ ...config, period: e.target.value })}
            >
              <option value="3mo">3 Months</option>
              <option value="6mo">6 Months</option>
              <option value="1y">1 Year</option>
              <option value="2y">2 Years</option>
              <option value="5y">5 Years</option>
            </select>
          </label>
          <label>
            Execution Action
            <select value={config.action} disabled>
              <option value="buy">BUY (Long-only)</option>
            </select>
          </label>
        </div>
      </section>

      <div className="creator-grid">
        <RuleBuilder
          title="Entry Signal Rule"
          group={config.entry}
          catalog={catalog}
          onChange={setEntry}
        />
        <RuleBuilder
          title="Exit Signal Rule"
          group={config.exit}
          catalog={catalog}
          onChange={setExit}
        />
      </div>

      {error && <div className="error">{error}</div>}
      {status && <div className="success">{status}</div>}

      <div className="creator-actions">
        <button type="submit" disabled={loading}>
          {loading ? "Saving…" : strategyId ? "Update Strategy Config" : "Save Strategy Config"}
        </button>
      </div>
    </form>
  );
}
