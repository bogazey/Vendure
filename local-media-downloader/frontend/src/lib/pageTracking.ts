import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import i18n from "../i18n";
import { api } from "../services/api";

/**
 * Fires one first-party page_view per SPA navigation (see routes_analytics.py
 * for the server-side validation/whitelisting). Analytics must never break
 * the app - the request is fire-and-forget and any failure (network,
 * ad-blocker on an unrelated rule, rate limit) is swallowed silently, never
 * surfaced to the user.
 *
 * The ref-based guard prevents two known sources of duplicate counting:
 * React 18 StrictMode's dev-only double-invoke of effects on mount (the
 * second invocation sees the same already-tracked path and skips), and a
 * route re-render that doesn't actually change the pathname (e.g. only the
 * query string changes).
 */
export function usePageViewTracking(): void {
  const location = useLocation();
  const lastTracked = useRef<string | null>(null);

  useEffect(() => {
    const path = location.pathname;
    if (lastTracked.current === path) return;
    lastTracked.current = path;

    const params = new URLSearchParams(location.search);
    api
      .trackEvent({
        event_type: "page_view",
        path,
        locale: i18n.language?.startsWith("ar") ? "ar" : "en",
        referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
        utm_source: params.get("utm_source") || undefined,
        utm_medium: params.get("utm_medium") || undefined,
        utm_campaign: params.get("utm_campaign") || undefined,
      })
      .catch(() => {
        // Silent by design - see the docstring above.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);
}
