"use client";

import { FormEvent, useEffect, useState } from "react";
import { AlertRule, api, StrategyInfo, TelegramChat } from "@/lib/api";
import { DATA_INTERVALS } from "@/lib/intervals";

function defaultPeriodForInterval(interval: string): string {
  if (interval === "1m" || interval === "2m") return "5d";
  if (["5m", "15m", "30m"].includes(interval)) return "1mo";
  if (["60m", "90m", "1h"].includes(interval)) return "3mo";
  if (["5d", "1wk", "1mo", "3mo"].includes(interval)) return "2y";
  return "3mo";
}

function strategyLabel(s: StrategyInfo): string {
  if (s.source === "generated" || s.id.startsWith("gen_")) {
    return s.name.startsWith("[Python]") ? s.name : `[Python] ${s.name}`;
  }
  if (s.source === "custom") return `★ ${s.name}`;
  return s.name;
}

/** Preview of the Telegram message shape (matches backend formatter). */
function previewMessage(opts: {
  alertType: string;
  side: string;
  symbol: string;
  interval: string;
  strategyId: string;
  ruleName: string;
}): string {
  const strategy = opts.strategyId || "oro_swing_adaptive";
  if (opts.alertType === "ENTRADA") {
    return [
      `[ENTRADA] ${opts.symbol || "GC=F"} · ${opts.interval} · ${opts.side}`,
      "",
      `Estrategia: ${strategy}`,
      `Regla: ${opts.ruleName || "Mi alerta"}`,
      "",
      "Niveles para el broker:",
      "  Entrada: 2650.50",
      "  SL:     2635.20  (−15.30 pts)",
      "  TP:     2681.10  (+30.60 pts)",
      "",
      "Precio actual: 2650.50",
      "Motivo: Señal de entrada",
      "Estado: ABIERTA",
      "Hora: 2026-07-24 15:45",
    ].join("\n");
  }
  return [
    `[SALIDA] ${opts.symbol || "GC=F"} · ${opts.interval} · ${opts.side}`,
    "",
    `Estrategia: ${strategy}`,
    `Regla: ${opts.ruleName || "Mi alerta"}`,
    "",
    "Precio: 2681.10",
    "Entrada: 2650.50",
    "Salida: 2681.10",
    "SL: 2635.20  (−15.30 pts)",
    "TP: 2681.10  (+30.60 pts)",
    "Motivo: Take profit (TP)",
    "Estado: CERRADA",
    "Hora: 2026-07-24 16:10",
  ].join("\n");
}

export default function AlertsPage() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [chats, setChats] = useState<TelegramChat[]>([]);
  const [message, setMessage] = useState("Test alert from Trading Lab");
  const [name, setName] = useState("QQQ VWAP 5m");
  const [strategyId, setStrategyId] = useState("");
  const [symbol, setSymbol] = useState("QQQ");
  const [interval, setInterval] = useState("5m");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatName, setChatName] = useState("Mi chat");
  const [chatId, setChatId] = useState("");
  const [editingChatId, setEditingChatId] = useState<string>("");
  const [editingChatName, setEditingChatName] = useState("");
  const [editingChatValue, setEditingChatValue] = useState("");

  async function refresh() {
    const [strategyList, ruleList, chatList] = await Promise.all([
      api.getStrategies(),
      api.getAlertRules(),
      api.getTelegramChats(),
    ]);
    setStrategies(strategyList);
    setRules(ruleList);
    setChats(chatList);
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
        interval,
        period: defaultPeriodForInterval(interval),
        parameters: {},
        enabled: true,
        notify_on: ["entry", "exit"],
      });
      setStatus(`Alert rule saved (${interval}).`);
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

  async function addChat(event: FormEvent) {
    event.preventDefault();
    setError("");
    setStatus("");
    try {
      await api.createTelegramChat({ name: chatName, chat_id: chatId });
      setStatus("Telegram chat added.");
      setChatId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add chat");
    }
  }

  async function removeChat(chatEntryId?: string) {
    if (!chatEntryId) return;
    await api.deleteTelegramChat(chatEntryId);
    await refresh();
  }

  function startEditChat(chat: TelegramChat) {
    setEditingChatId(chat.id);
    setEditingChatName(chat.name);
    setEditingChatValue(chat.chat_id);
  }

  function cancelEditChat() {
    setEditingChatId("");
    setEditingChatName("");
    setEditingChatValue("");
  }

  async function saveEditChat(chatEntryId: string) {
    setError("");
    setStatus("");
    try {
      await api.updateTelegramChat(chatEntryId, {
        name: editingChatName,
        chat_id: editingChatValue,
      });
      setStatus("Telegram chat updated.");
      cancelEditChat();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update chat");
    }
  }

  async function toggleChatEnabled(chat: TelegramChat) {
    setError("");
    setStatus("");
    try {
      await api.updateTelegramChat(chat.id, { enabled: !chat.enabled });
      setStatus(`Chat ${chat.name} ${chat.enabled ? "disabled" : "enabled"}.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update chat");
    }
  }

  async function runCheck() {
    setError("");
    setStatus("");
    try {
      const body = await api.checkAlerts();
      const results = body.results || [];
      const fired = results.filter(
        (r) =>
          Boolean(r.event) &&
          !["none", "insufficient_data", "already_sent"].includes(r.event!)
      );
      setStatus(
        `Checked ${results.length} rule(s)` +
          (fired.length ? ` · ${fired.length} alert(s) sent` : " · no new signals")
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check failed");
    }
  }

  const previewEntry = previewMessage({
    alertType: "ENTRADA",
    side: "LONG",
    symbol,
    interval,
    strategyId,
    ruleName: name,
  });
  const previewExit = previewMessage({
    alertType: "SALIDA",
    side: "LONG",
    symbol,
    interval,
    strategyId,
    ruleName: name,
  });

  return (
    <div className="stack">
      <div>
        <h1>Alerts</h1>
        <p className="muted">
          Rules are checked automatically every minute by the backend (configurable via{" "}
          <code>ALERT_CHECK_INTERVAL_SECONDS</code>). You can also run{" "}
          <strong>Check rules now</strong> or Telegram <code>/check</code>. Bot commands:{" "}
          <code>/help</code>, <code>/list</code>, <code>/state</code>, <code>/enable</code>,{" "}
          <code>/disable</code>, <code>/chats</code>, <code>/chat_on</code>, <code>/chat_off</code>.
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
                  {strategyLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Symbol
            <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          </label>
          <label>
            Candle interval
            <select value={interval} onChange={(e) => setInterval(e.target.value)}>
              {DATA_INTERVALS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button type="submit">Save rule</button>
      </form>

      <section className="panel stack">
        <h2>Message preview</h2>
        <p className="muted">
          Formato de Telegram para <strong>entrada</strong> y <strong>salida</strong> (las dos
          se envían cuando hay señal).
        </p>
        <div className="row" style={{ alignItems: "stretch" }}>
          <pre className="alert-preview" style={{ flex: 1 }}>
            {previewEntry}
          </pre>
          <pre className="alert-preview" style={{ flex: 1 }}>
            {previewExit}
          </pre>
        </div>
      </section>

      {status && <div className="success">{status}</div>}
      {error && <div className="error">{error}</div>}

      <section className="panel stack">
        <h2>Telegram chats</h2>
        <p className="muted">
          Añade los chats que van a recibir tus alertas. A cada chat le das un nombre
          para poder distinguirlos.
        </p>

        <form className="row" onSubmit={addChat}>
          <label>
            Nombre
            <input value={chatName} onChange={(e) => setChatName(e.target.value)} />
          </label>
          <label>
            Chat id
            <input
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="Ej: 123456789"
            />
          </label>
          <button type="submit">Add</button>
        </form>

        {chats.length === 0 ? (
          <p className="muted">No hay chats configurados aún.</p>
        ) : (
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Chat ID</th>
                  <th>Enabled</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {chats.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {editingChatId === c.id ? (
                        <input
                          value={editingChatName}
                          onChange={(e) => setEditingChatName(e.target.value)}
                        />
                      ) : (
                        c.name
                      )}
                    </td>
                    <td>
                      {editingChatId === c.id ? (
                        <input
                          value={editingChatValue}
                          onChange={(e) => setEditingChatValue(e.target.value)}
                        />
                      ) : (
                        c.chat_id
                      )}
                    </td>
                    <td>{c.enabled ? "yes" : "no"}</td>
                    <td>
                      <div className="row" style={{ gap: 8 }}>
                        {editingChatId === c.id ? (
                          <>
                            <button type="button" onClick={() => saveEditChat(c.id)}>
                              Save
                            </button>
                            <button className="secondary" type="button" onClick={cancelEditChat}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => toggleChatEnabled(c)}
                            >
                              {c.enabled ? "Disable" : "Enable"}
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => startEditChat(c)}
                            >
                              Edit
                            </button>
                            <button
                              className="secondary"
                              type="button"
                              onClick={() => removeChat(c.id)}
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel stack">
        <h2>Saved rules</h2>
        <button className="secondary" type="button" onClick={runCheck}>
          Check rules now
        </button>
        {rules.length === 0 ? (
          <p className="muted">No rules yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Strategy</th>
                  <th>Symbol</th>
                  <th>Interval</th>
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
                    <td>{rule.interval || "1d"}</td>
                    <td>{rule.enabled ? "yes" : "no"}</td>
                    <td>
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => removeRule(rule.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
