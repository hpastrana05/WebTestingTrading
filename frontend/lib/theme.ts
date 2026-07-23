export type ThemeId = "forest" | "ocean" | "slate" | "ember" | "light";

export type ThemePrefs = {
  theme: ThemeId;
  /** Optional hex override for --accent */
  accent: string | null;
  /** Optional hex override for page background base */
  background: string | null;
};

export const THEME_STORAGE_KEY = "trading-lab-theme";
export const THEME_COOKIE = "tl_theme";

export const THEME_OPTIONS: { id: ThemeId; label: string; swatch: string }[] = [
  { id: "forest", label: "Forest", swatch: "#3d9b6e" },
  { id: "ocean", label: "Ocean", swatch: "#3d7eb8" },
  { id: "slate", label: "Slate", swatch: "#7a8794" },
  { id: "ember", label: "Ember", swatch: "#d4784a" },
  { id: "light", label: "Light", swatch: "#e8eee9" },
];

export const DEFAULT_THEME_PREFS: ThemePrefs = {
  theme: "forest",
  accent: null,
  background: null,
};

export function parseThemePrefs(raw: string | null | undefined): ThemePrefs {
  if (!raw) return { ...DEFAULT_THEME_PREFS };
  try {
    const data = JSON.parse(raw) as Partial<ThemePrefs>;
    const theme = THEME_OPTIONS.some((t) => t.id === data.theme)
      ? (data.theme as ThemeId)
      : "forest";
    return {
      theme,
      accent: typeof data.accent === "string" && /^#[0-9a-fA-F]{6}$/.test(data.accent)
        ? data.accent
        : null,
      background:
        typeof data.background === "string" && /^#[0-9a-fA-F]{6}$/.test(data.background)
          ? data.background
          : null,
    };
  } catch {
    return { ...DEFAULT_THEME_PREFS };
  }
}

/** Apply prefs to <html> for immediate paint / client updates. */
export function applyThemePrefs(prefs: ThemePrefs, root: HTMLElement = document.documentElement) {
  root.setAttribute("data-theme", prefs.theme);
  if (prefs.accent) {
    root.style.setProperty("--accent", prefs.accent);
    root.style.setProperty("--accent-deep", shadeHex(prefs.accent, -0.28));
    root.style.setProperty("--glow-1", hexToRgba(prefs.accent, 0.18));
  } else {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-deep");
    root.style.removeProperty("--glow-1");
  }
  if (prefs.background) {
    root.style.setProperty("--bg", prefs.background);
    root.style.setProperty("--bg-top", shadeHex(prefs.background, 0.06));
    root.style.setProperty("--bg-deep", shadeHex(prefs.background, -0.08));
    root.style.setProperty("--input-bg", shadeHex(prefs.background, -0.04));
  } else {
    root.style.removeProperty("--bg");
    root.style.removeProperty("--bg-top");
    root.style.removeProperty("--bg-deep");
    root.style.removeProperty("--input-bg");
  }
}

export function saveThemePrefs(prefs: ThemePrefs) {
  const raw = JSON.stringify(prefs);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, raw);
  } catch {
    /* private mode */
  }
  // Cookie backup (1 year) so preference can survive across simple restores
  const maxAge = 60 * 60 * 24 * 365;
  document.cookie = `${THEME_COOKIE}=${encodeURIComponent(raw)};path=/;max-age=${maxAge};samesite=lax`;
}

export function loadThemePrefs(): ThemePrefs {
  try {
    const fromLs = localStorage.getItem(THEME_STORAGE_KEY);
    if (fromLs) return parseThemePrefs(fromLs);
  } catch {
    /* ignore */
  }
  if (typeof document !== "undefined") {
    const match = document.cookie.match(new RegExp(`(?:^|; )${THEME_COOKIE}=([^;]*)`));
    if (match) return parseThemePrefs(decodeURIComponent(match[1]));
  }
  return { ...DEFAULT_THEME_PREFS };
}

function hexToRgba(hex: string, alpha: number): string {
  const n = hex.replace("#", "");
  const r = parseInt(n.slice(0, 2), 16);
  const g = parseInt(n.slice(2, 4), 16);
  const b = parseInt(n.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** amount: -1..1 darken/lighten */
function shadeHex(hex: string, amount: number): string {
  const n = hex.replace("#", "");
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  const channel = (start: number) => {
    const c = parseInt(n.slice(start, start + 2), 16);
    return clamp(c + 255 * amount);
  };
  const r = channel(0);
  const g = channel(2);
  const b = channel(4);
  return `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** Inline script for layout — prevents flash of wrong theme. */
export const THEME_BOOT_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}";var c="${THEME_COOKIE}";var raw=localStorage.getItem(k);if(!raw){var m=document.cookie.match(new RegExp("(?:^|; )"+c+"=([^;]*)"));if(m)raw=decodeURIComponent(m[1]);}if(!raw)return;var p=JSON.parse(raw);var root=document.documentElement;if(p.theme)root.setAttribute("data-theme",p.theme);function shade(hex,a){var n=hex.replace("#","");function ch(s){var v=parseInt(n.slice(s,s+2),16);v=Math.round(v+255*a);return Math.max(0,Math.min(255,v)).toString(16).padStart(2,"0");}return"#"+ch(0)+ch(2)+ch(4);}function rgba(hex,a){var n=hex.replace("#","");return"rgba("+parseInt(n.slice(0,2),16)+","+parseInt(n.slice(2,4),16)+","+parseInt(n.slice(4,6),16)+","+a+")";}if(p.accent&&/^#[0-9a-fA-F]{6}$/.test(p.accent)){root.style.setProperty("--accent",p.accent);root.style.setProperty("--accent-deep",shade(p.accent,-0.28));root.style.setProperty("--glow-1",rgba(p.accent,0.18));}if(p.background&&/^#[0-9a-fA-F]{6}$/.test(p.background)){root.style.setProperty("--bg",p.background);root.style.setProperty("--bg-top",shade(p.background,0.06));root.style.setProperty("--bg-deep",shade(p.background,-0.08));root.style.setProperty("--input-bg",shade(p.background,-0.04));}}catch(e){}})();`;
