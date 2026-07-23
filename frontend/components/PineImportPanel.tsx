"use client";

import { DragEvent, useRef, useState } from "react";
import { api, StrategyConfig } from "@/lib/api";

type Props = {
  onImported: (config: Omit<StrategyConfig, "id">, warnings: string[]) => void;
};

export default function PineImportPanel({ onImported }: Props) {
  const [code, setCode] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function readFile(file: File) {
    const text = await file.text();
    setCode(text);
    setFileName(file.name);
    setError("");
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
    try {
      if (!code.trim()) {
        throw new Error("Paste Pine Script or drop a .pine file first.");
      }
      const result = await api.importPine(code);
      const { id: _id, ...draft } = result.config;
      onImported(draft, result.warnings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel stack pine-import">
      <div>
        <h2>Import from Pine Script</h2>
        <p className="muted">
          Drop a <code>.pine</code> file or paste TradingView strategy code. We convert what
          maps to the Strategy Creator (crosses, EMA/SMA/VWAP/RSI, sessions, ATR/R:R). Review
          the result — this is not a full Pine interpreter.
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

      <div className="row" style={{ justifyContent: "flex-start" }}>
        <button type="button" onClick={convert} disabled={loading}>
          {loading ? "Converting…" : "Convert to strategy"}
        </button>
        {code && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setCode("");
              setFileName("");
              setError("");
            }}
          >
            Clear
          </button>
        )}
      </div>
    </section>
  );
}
