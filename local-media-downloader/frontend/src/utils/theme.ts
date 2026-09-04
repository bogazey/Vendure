import type { Theme } from "../types/api";

const STORAGE_KEY = "lmd-theme-preference";

/**
 * Loady's dark navy/glass look is the confirmed brand identity, not a
 * convenience that tracks the visitor's OS appearance - "system" used to
 * mean "follow prefers-color-scheme," which silently showed the pale
 * accessibility-fallback light theme to anyone whose OS/browser wasn't in
 * dark mode (read as "a bright SaaS landing page" instead of Loady).
 * "system" now always resolves to dark; the light theme is only ever shown
 * when a user explicitly picks "Light" in Settings.
 */
export function resolveTheme(theme: Theme): "light" | "dark" {
  return theme === "light" ? "light" : "dark";
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
