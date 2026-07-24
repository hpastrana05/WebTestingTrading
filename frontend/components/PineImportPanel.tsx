"use client";

import { DragEvent, useRef, useState } from "react";
import { api, StrategyConfig } from "@/lib/api";

type Props = {
  onImported: (
    config: Omit<StrategyConfig, "id">,
    warnings: string[],
    meta?: { pythonCode: string; filename: string; strategyId: string }
  ) => void;
};

export default function PineImportPanel({ onImported }: Props) {
  const [code, setCode] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [fileName, setFileName] = useState("");
  const [pythonCode, setPythonCode] = useState("");
  const [pythonFilename, setPythonFilename] = useState("");
  const [strategyId, setStrategyId] = useState("");
  const [draft, setDraft] = useState<Omit<StrategyConfig, "id"> | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [reliability, setReliability] = useState("");
  const [acked, setAcked] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function readFile(file: File) {
    const text = await file.text();
    setCode(text);
    setFileName(file.name);
    setError("");
    setStatus("");
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) return;
    if (
      !/\.(pine|txt|ps)$/i.test(file.name) &&
      !file.type.startsWith("text/") &&
      file.type !== ""
    ) {
      setError("Drop a .pine or .txt file, or paste the code below.");
      return;
    }
    readFile(file).catch((err: Error) => setError(err.message));
  }

  async function convert() {
    setLoading(true);
    setError("");
    setStatus("");
    setAcked(false);
    try {
      if (!code.trim()) {
        throw new Error("Paste Pine Script or drop a .pine file first.");
      }
      const result = await api.importPine(code);
      const { id: _id, ...cfg } = result.config;
      setDraft(cfg);
      setWarnings(result.warnings);
      setReliability(result.reliability || "");
      setPythonCode(result.python_code || "");
      setPythonFilename(result.python_filename || "generated_strategy.py");
      setStrategyId(result.strategy_id || "");
      setStatus("Draft ready — read the reliability warning, then load or save after review.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  function requireAck(): boolean {
    if (!acked) {
      setError("Confirm that you understand the import is not 100% reliable before continuing.");
      return false;
    }
    return true;
  }

  function loadCreator() {
    if (!draft || !requireAck()) return;
    onImported(draft, warnings, {
      pythonCode,
      filename: pythonFilename,
      strategyId,
    });
  }

  async function savePython() {
    if (!requireAck()) return;
    setSaving(true);
    setError("");
    setStatus("");
    try {
      if (!code.trim()) {
        throw new Error("Paste Pine Script first.");
      }
      const saved = await api.savePineAsPython(code);
      setPythonCode(saved.python_code);
      setPythonFilename(saved.filename);
      setStrategyId(saved.id);
      setWarnings(saved.warnings);
      setStatus(
        `Saved Python strategy “${saved.name}” (id: ${saved.id}). Review it in Backtest before trusting results.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function downloadPython() {
    if (!pythonCode) return;
    const blob = new Blob([pythonCode], { type: "text/x-python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = pythonFilename || "generated_strategy.py";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyPython() {
    if (!pythonCode) return;
    try {
      await navigator.clipboard.writeText(pythonCode);
      setStatus("Python copied to clipboard.");
    } catch {
      setError("Could not copy to clipboard.");
    }
  }

  return (
    <section className="panel stack pine-import">
      <div>
        <h2>Import from Pine Script</h2>
        <p className="muted">
          Converts what we can into Strategy Creator rules and/or a Python wrapper. This is{" "}
          <strong>not</strong> TradingView’s Pine engine.
        </p>
      </div>

      <div className="pine-disclaimer" role="note">
        <strong>Not 100% reliable — always review</strong>
        <p>
          The importer is approximate. Complex logic (loops, <code>var</code> state, anti-streak
          / <code>closedtrades</code>, ternaries, trailing stops, custom sizing, multi-timeframe, …)
          is skipped or guessed. Backtest results will differ from TradingView. Treat every import
          as a draft and verify rules before use.
        </p>
      </div>

      <div
        className={`pine-dropzone${dragging ? " is-dragging" : ""}`}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        <strong>Drop Pine Script here</strong>
        <span className="muted">
          {fileName ? `Loaded: ${fileName}` : "or click to choose a .pine / .txt file"}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept=".pine,.txt,.ps,text/plain"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              readFile(file).catch((err: Error) => setError(err.message));
            }
          }}
        />
      </div>

      <label>
        Or paste code
        <textarea
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder={'//@version=5\nstrategy("My Strategy", overlay=true)\n...'}
          rows={10}
          className="pine-code"
        />
      </label>

      {error && <div className="error">{error}</div>}
      {status && <div className="success">{status}</div>}

      <div className="row" style={{ justifyContent: "flex-start" }}>
        <button type="button" onClick={convert} disabled={loading}>
          {loading ? "Converting…" : "Convert"}
        </button>
        {code && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setCode("");
              setFileName("");
              setError("");
              setStatus("");
              setDraft(null);
              setPythonCode("");
              setWarnings([]);
              setReliability("");
              setAcked(false);
            }}
          >
            Clear
          </button>
        )}
      </div>

      {draft && (
        <>
          <div className="pine-disclaimer pine-disclaimer-strong" role="alert">
            <strong>Review required before use</strong>
            {reliability ? <p className="pine-reliability">{reliability}</p> : null}
            <p>
              This conversion is <strong>not fully faithful</strong> to your Pine Script. Check
              every condition, session, and exit in the Creator (or the generated Python) before
              backtesting.
            </p>
            <label className="checkbox-label pine-ack">
              <input
                type="checkbox"
                checked={acked}
                onChange={(e) => {
                  setAcked(e.target.checked);
                  if (e.target.checked) setError("");
                }}
              />
              I understand this import is not 100% reliable and I will review it
            </label>
          </div>

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

          <div className="row" style={{ justifyContent: "flex-start" }}>
            <button type="button" onClick={loadCreator} disabled={!acked}>
              Load in Strategy Creator
            </button>
            <button
              type="button"
              className="secondary"
              onClick={savePython}
              disabled={saving || !acked}
            >
              {saving ? "Saving…" : "Save as Python strategy"}
            </button>
          </div>
        </>
      )}

      {pythonCode && (
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Generated Python (draft)</h3>
            <div className="row" style={{ flex: "0 0 auto" }}>
              <button type="button" className="secondary" onClick={copyPython}>
                Copy
              </button>
              <button type="button" className="secondary" onClick={downloadPython}>
                Download .py
              </button>
            </div>
          </div>
          <p className="muted">
            File: <code>{pythonFilename}</code>
            {strategyId ? (
              <>
                {" "}
                · id: <code>{strategyId}</code>
              </>
            ) : null}{" "}
            — wraps imported rules; not a full Pine port.
          </p>
          <textarea className="pine-code" value={pythonCode} readOnly rows={16} />
        </div>
      )}
    </section>
  );
}
