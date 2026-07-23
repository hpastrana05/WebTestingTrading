"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertRule, api, StrategyInfo } from "@/lib/api";

export default function AlertsPage() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [message, setMessage] = useState("Test alert from Trading Lab");
  const [name, setName] = useState("AAPL SMA entries");
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("AAPL");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    const [strategyList, ruleList] = await Promise.all([
      api.getStrategies(),
      api.getAlertRules(),
    ]);
    setStrategies(strategyList);
    setRules(ruleList);
    if (!strategyId && strategyList[0]) setStrategyId(strategyList[0].id);
  }

  useEffect(() => {
    refresh().catch((err: Error) => setError(err.message));
  }, []);

  async function sendTest(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setStatus("");
    try {
      await api.sendAlert(message);
      setStatus("Telegram message sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setLoading(false);
    }
  }

  async function createRule(event: FormEvent) {
    event.preventDefault();
    setError("");
    setStatus("");
    try {
      await api.createAlertRule({
        name,
        strategy_id: strategyId,
        symbol,
        parameters: {},
        enabled: true,
        notify_on: ["entry", "exit"],
      });
      setStatus("Alert rule saved.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rule");
    }
  }

  async function removeRule(id?: string) {
    if (!id) return;
    await api.deleteAlertRule(id);
    await refresh();
  }

  async function runCheck() {
    setError("");
    setStatus("");
    try {
      const body = await api.checkAlerts();
      setStatus(`Checked ${body.results?.length ?? 0} rule(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check failed");
    }
  }

  return (
    <div className="stack">
      <div>
        <h1>Alerts</h1>
        <p className="muted">
          Send Telegram messages and keep simple alert rules for later automation.
        </p>
      </div>

      <form className="panel stack" onSubmit={sendTest}>
        <h2>Send test message</h2>
        <label>
          Message
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Sending…" : "Send to Telegram"}
        </button>
      </form>

      <form className="panel stack" onSubmit={createRule}>
        <h2>Alert rule</h2>
        <div className="row">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
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
        </div>
        <button type="submit">Save rule</button>
      </form>

      {status && <div className="success">{status}</div>}
      {error && <div className="error">{error}</div>}

      <section className="panel stack">
        <h2>Saved rules</h2>
        <button className="secondary" type="button" onClick={runCheck}>
          Check rules now
        </button>
        {rules.length === 0 ? (
          <p className="muted">No rules yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Strategy</th>
                <th>Symbol</th>
                <th>Enabled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.name}</td>
                  <td>{rule.strategy_id}</td>
                  <td>{rule.symbol}</td>
                  <td>{rule.enabled ? "yes" : "no"}</td>
                  <td>
                    <button className="secondary" type="button" onClick={() => removeRule(rule.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
