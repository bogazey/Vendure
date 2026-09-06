import { useEffect } from "react";

/**
 * Marks the current page noindex,nofollow for as long as this component
 * is mounted - the actual mechanism behind Section 12's "private pages
 * must not be indexed" requirement. Deliberately NOT implemented via
 * robots.txt Disallow: disallowing a URL stops a crawler from ever
 * fetching it, which means it can never see this directive either - a
 * disallowed-but-linked URL can still appear indexed with no snippet.
 * A live noindex meta tag (which Google's JS-executing crawler does see)
 * is the correct, authoritative signal; robots.txt Disallow entries for
 * these same paths (see public/robots.txt) are just a crawl-budget
 * courtesy on top, not the enforcement mechanism.
 *
 * Used centrally by ProtectedRoute/AdminRoute/GuestAllowedRoute (every
 * authenticated app route) and directly by the standalone auth pages
 * (login/signup/password reset/etc.) that aren't behind those guards.
 */
export function useNoindex(): void {
  useEffect(() => {
    const existing = document.head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    const previousContent = existing?.getAttribute("content") ?? null;
    const meta = existing ?? document.createElement("meta");
    if (!existing) {
      meta.setAttribute("name", "robots");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", "noindex, nofollow");

    return () => {
      if (existing) {
        if (previousContent !== null) meta.setAttribute("content", previousContent);
      } else {
        meta.remove();
      }
    };
  }, []);
}
