"use client";

import { useEffect, useRef, useState } from "react";
import {
  DEFAULT_THEME_PREFS,
  THEME_OPTIONS,
  ThemePrefs,
  applyThemePrefs,
  loadThemePrefs,
  saveThemePrefs,
} from "@/lib/theme";

export default function ThemeControls() {
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState<ThemePrefs>(DEFAULT_THEME_PREFS);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loaded = loadThemePrefs();
    setPrefs(loaded);
    applyThemePrefs(loaded);
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!panelRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function update(next: ThemePrefs) {
    setPrefs(next);
    applyThemePrefs(next);
    saveThemePrefs(next);
  }

  return (
    <div className="theme-controls" ref={panelRef}>
      <button
        type="button"
        className="theme-toggle secondary"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
        title="Appearance"
      >
        Theme
      </button>

      {open && (
        <div className="theme-panel" role="dialog" aria-label="Appearance settings">
          <div className="theme-panel-head">
            <strong>Appearance</strong>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                update({ ...DEFAULT_THEME_PREFS });
              }}
            >
              Reset
            </button>
          </div>

          <p className="muted theme-hint">Saved in this browser (localStorage + cookie).</p>

          <div className="theme-presets" role="listbox" aria-label="Theme preset">
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                role="option"
                aria-selected={prefs.theme === opt.id}
                className={`theme-preset${prefs.theme === opt.id ? " is-active" : ""}`}
                onClick={() => update({ ...prefs, theme: opt.id })}
              >
                <span className="theme-swatch" style={{ background: opt.swatch }} />
                {opt.label}
              </button>
            ))}
          </div>

          <div className="theme-custom row">
            <label>
              Accent color
              <input
                type="color"
                value={prefs.accent || THEME_OPTIONS.find((t) => t.id === prefs.theme)?.swatch || "#3d9b6e"}
                onChange={(e) => update({ ...prefs, accent: e.target.value })}
              />
            </label>
            <label>
              Background
              <input
                type="color"
                value={prefs.background || (prefs.theme === "light" ? "#e8eee9" : "#0f1412")}
                onChange={(e) => update({ ...prefs, background: e.target.value })}
              />
            </label>
          </div>

          <div className="row" style={{ justifyContent: "flex-start" }}>
            {(prefs.accent || prefs.background) && (
              <button
                type="button"
                className="secondary"
                onClick={() => update({ ...prefs, accent: null, background: null })}
              >
                Clear custom colors
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
