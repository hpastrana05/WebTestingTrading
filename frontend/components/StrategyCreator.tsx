"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import RuleBuilder, {
  emptyGroup,
  emptyStructureAtr,
  normalizeGroup,
} from "@/components/RuleBuilder";
import PineImportPanel from "@/components/PineImportPanel";
import {
  api,
  IndicatorCatalog,
  RuleNode,
  StrategyConfig,
} from "@/lib/api";
import { DATA_INTERVALS } from "@/lib/intervals";
import { DATA_PERIODS } from "@/lib/periods";

type Props = {
  strategyId?: string;
};

function cond(
  left: RuleNode["left"],
  operator: string,
  right: RuleNode["right"],
  right_scale = 1
): RuleNode {
  return { type: "condition", left, operator, right, right_scale };
}

/** Closest Strategy Creator recreation of the Pine VWAP Momentum Pro script. */
function vwapMomentumTemplate(): Omit<StrategyConfig, "id"> {
  const longEntry: RuleNode = {
    type: "group",
    logic: "all",
    children: [
      cond(
        { kind: "price", field: "Close" },
        "cross_above",
        { kind: "indicator", indicator: "vwap", params: {}, output: "VWAP" }
      ),
      cond(
        { kind: "price", field: "Close" },
        ">",
        { kind: "indicator", indicator: "ema", params: { length: 20 }, output: "EMA" }
      ),
      cond(
        { kind: "price", field: "BarRange" },
        ">",
        { kind: "indicator", indicator: "range_sma", params: { length: 15 }, output: "RANGE_SMA" },
        1.1
      ),
    ],
  };

  const shortEntry: RuleNode = {
    type: "group",
    logic: "all",
    children: [
      cond(
        { kind: "price", field: "Close" },
        "cross_below",
        { kind: "indicator", indicator: "vwap", params: {}, output: "VWAP" }
      ),
      cond(
        { kind: "price", field: "Close" },
        "<",
        { kind: "indicator", indicator: "ema", params: { length: 20 }, output: "EMA" }
      ),
      cond(
        { kind: "price", field: "BarRange" },
        ">",
        { kind: "indicator", indicator: "range_sma", params: { length: 15 }, output: "RANGE_SMA" },
        1.1
      ),
    ],
  };

  return {
    name: "VWAP Momentum Pro (Creator)",
    broker_ticker: "",
    yahoo_ticker: "QQQ",
    interval: "5m",
    period: "5d",
    direction: "both",
    trade_session: "1545-1930",
    close_session: "2150-2200",
    timezone: "Europe/Madrid",
    one_trade_per_day: true,
    entry: longEntry,
    entry_short: shortEntry,
    exit: {
      type: "group",
      logic: "any",
      children: [emptyStructureAtr(14, 1.1, 2.3)],
    },
  };
}

const defaultConfig = (): Omit<StrategyConfig, "id"> => ({
  name: "",
  broker_ticker: "",
  yahoo_ticker: "AAPL",
  interval: "1d",
  period: "1y",
  direction: "long",
  trade_session: "",
  close_session: "",
  timezone: "Europe/Madrid",
  one_trade_per_day: false,
  entry: emptyGroup("all"),
  entry_short: emptyGroup("all"),
  exit: emptyGroup("any"),
});

function applyImported(
  saved: Omit<StrategyConfig, "id"> | StrategyConfig
): Omit<StrategyConfig, "id"> {
  return {
    name: saved.name,
    broker_ticker: saved.broker_ticker || "",
    yahoo_ticker: saved.yahoo_ticker || "AAPL",
    interval: saved.interval || "1d",
    period: saved.period || "1y",
    direction: saved.direction || "long",
    trade_session: saved.trade_session || "",
    close_session: saved.close_session || "",
    timezone: saved.timezone || "Europe/Madrid",
    one_trade_per_day: Boolean(saved.one_trade_per_day),
    entry: normalizeGroup(saved.entry),
    entry_short: normalizeGroup(saved.entry_short || emptyGroup("all")),
    exit: normalizeGroup(saved.exit),
  };
}

export default function StrategyCreator({ strategyId }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [catalog, setCatalog] = useState<IndicatorCatalog | null>(null);
  const [config, setConfig] = useState(defaultConfig());
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [showImport, setShowImport] = useState(
    () => !strategyId || searchParams.get("import") === "pine"
  );

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
        setConfig(applyImported(saved));
      })
      .catch((err: Error) => setError(err.message));
  }, [strategyId]);

  function setEntry(entry: RuleNode) {
    setConfig((prev) => ({ ...prev, entry }));
  }

  function setEntryShort(entry_short: RuleNode) {
    setConfig((prev) => ({ ...prev, entry_short }));
  }

  function setExit(exit: RuleNode) {
    setConfig((prev) => ({ ...prev, exit }));
  }

  function onPineImported(draft: Omit<StrategyConfig, "id">, notes: string[]) {
    setConfig(applyImported(draft));
    setWarnings(notes);
    setStatus("Pine Script converted — review rules below, then save.");
    setError("");
    setShowImport(false);
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
        throw new Error(
          config.direction === "both"
            ? "Add at least one Long entry signal"
            : "Add at least one entry signal"
        );
      }
      if (
        config.direction === "both" &&
        !(config.entry_short.children && config.entry_short.children.length)
      ) {
        throw new Error("Add at least one Short entry signal");
      }
      if (!(config.exit.children && config.exit.children.length)) {
        throw new Error("Add at least one exit signal (or TP/SL / ATR R:R)");
      }

      const payload: Omit<StrategyConfig, "id"> = {
        ...config,
        entry: normalizeGroup(config.entry),
        entry_short: normalizeGroup(config.entry_short),
        exit: normalizeGroup(config.exit),
      };

      if (strategyId) {
        await api.updateStrategyConfig(strategyId, payload);
        setStatus("Strategy updated.");
      } else {
        const created = await api.createStrategyConfig(payload);
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

  const entryTitle =
    config.direction === "both"
      ? "Long Entry"
      : config.direction === "short"
        ? "Short Entry"
        : "Long Entry";

  return (
    <form className="stack creator" onSubmit={onSave}>
      <div className="creator-head">
        <div>
          <h1>Strategy Creator</h1>
          <p className="muted">
            Build entry/exit rules with sessions, impulse (× scale), VWAP, and ATR/R:R exits —
            or import from Pine Script.
          </p>
        </div>
        <div className="row" style={{ flex: "0 0 auto" }}>
          <button
            type="button"
            className="secondary"
            onClick={() => setShowImport((v) => !v)}
          >
            {showImport ? "Hide Pine import" : "Import Pine Script"}
          </button>
          {!strategyId && (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setConfig(vwapMomentumTemplate());
                setWarnings([]);
                setStatus("Loaded VWAP Momentum Pro template — review and save.");
              }}
            >
              Load VWAP Momentum template
            </button>
          )}
          <Link className="secondary-link" href="/strategies">
            ← Back to strategies
          </Link>
        </div>
      </div>

      {showImport && <PineImportPanel onImported={onPineImported} />}

      {warnings.length > 0 && (
        <div className="warning-list">
          <strong>Import notes</strong>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

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
              placeholder="QQQ"
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
              {DATA_INTERVALS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Default Data Period
            <select
              value={config.period}
              onChange={(e) => setConfig({ ...config, period: e.target.value })}
            >
              {DATA_PERIODS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direction
            <select
              value={config.direction}
              onChange={(e) =>
                setConfig({
                  ...config,
                  direction: e.target.value as "long" | "short" | "both",
                })
              }
            >
              <option value="long">Long</option>
              <option value="short">Short</option>
              <option value="both">Both</option>
            </select>
          </label>
        </div>
        <div className="row">
          <label>
            Trade session
            <input
              value={config.trade_session}
              onChange={(e) => setConfig({ ...config, trade_session: e.target.value })}
              placeholder="1545-1930 (empty = always)"
            />
          </label>
          <label>
            Forced close session
            <input
              value={config.close_session}
              onChange={(e) => setConfig({ ...config, close_session: e.target.value })}
              placeholder="2150-2200"
            />
          </label>
          <label>
            Timezone
            <input
              value={config.timezone}
              onChange={(e) => setConfig({ ...config, timezone: e.target.value })}
              placeholder="Europe/Madrid"
            />
          </label>
          <label className="checkbox-label">
            One trade / day
            <input
              type="checkbox"
              checked={config.one_trade_per_day}
              onChange={(e) =>
                setConfig({ ...config, one_trade_per_day: e.target.checked })
              }
            />
          </label>
        </div>
        {config.direction === "both" && (
          <p className="muted">
            Both requires separate Long and Short entry rules. Shared exit rules (including
            ATR/R:R) close whichever side is open.
          </p>
        )}
      </section>

      <div className="creator-grid">
        <RuleBuilder
          title={entryTitle}
          group={config.entry}
          catalog={catalog}
          onChange={setEntry}
        />
        {config.direction === "both" && (
          <RuleBuilder
            title="Short Entry"
            group={config.entry_short}
            catalog={catalog}
            onChange={setEntryShort}
          />
        )}
        <RuleBuilder
          title="Exit Rules"
          group={config.exit}
          catalog={catalog}
          onChange={setExit}
          allowRisk
          hint="Use % stop/target, or Structure ATR + R:R (SL = max(bar distance, ATR×mult), TP = SL×R:R)."
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
