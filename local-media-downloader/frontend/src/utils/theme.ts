import type { Theme } from "../types/api";

const STORAGE_KEY = "lmd-theme-preference";

function systemPrefersDark(): boolean {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
  } catch {
    return true;
  }
}

export function resolveTheme(theme: Theme): "light" | "dark" {
  return theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
}

/** Applies the theme to <html> and remembers it for the next page load. */
export function applyTheme(theme: Theme): void {
  const resolved = resolveTheme(theme);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.style.colorScheme = resolved;

  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // localStorage can be unavailable (private browsing); theme still
    // applies for the current page load, it just won't persist locally.
  }
}

/** Best-effort synchronous read used before the first paint to avoid a flash of the wrong theme. */
export function getCachedThemePreference(): Theme {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    // ignore
  }
  return "system";
}

let systemWatcherAttached = false;

/** Re-applies the theme whenever the OS preference changes, while the current setting is "system". */
export function watchSystemTheme(getCurrentTheme: () => Theme): void {
  if (systemWatcherAttached || !window.matchMedia) return;
  systemWatcherAttached = true;
  const mql = window.matchMedia("(prefers-color-scheme: dark)");
  const handler = () => {
    if (getCurrentTheme() === "system") applyTheme("system");
  };
  mql.addEventListener?.("change", handler);
}
