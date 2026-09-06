# Loady SEO — Phase 1 (bilingual foundation)

This document covers the bilingual (English/Arabic) SEO foundation added on
top of the existing Loady app: a small set of indexable, prerendered public
pages, plus the technical scaffolding (metadata, sitemap, robots, noindex,
structured data) needed for Google Search Console once `loady.cc` is live.

It does not cover content strategy, link building, or ranking tactics -
see "Recommended Phase 2 priorities" in the final report for what comes next.

## Contents

- [URL architecture](#url-architecture)
- [Rendering strategy](#rendering-strategy)
- [Language architecture](#language-architecture)
- [Canonical strategy](#canonical-strategy)
- [Sitemap](#sitemap)
- [Robots.txt](#robotstxt)
- [Noindex strategy](#noindex-strategy)
- [Structured data](#structured-data)
- [Production base URL configuration](#production-base-url-configuration)
- [Verifying the prerendered output](#verifying-the-prerendered-output)
- [Search Console setup (after loady.cc is live)](#search-console-setup-after-loadycc-is-live)
- [Analytics readiness](#analytics-readiness)
- [Content-quality rules](#content-quality-rules)
- [How to add a new bilingual SEO page](#how-to-add-a-new-bilingual-seo-page)
- [404 / status behavior](#404--status-behavior)
- [Known limitations](#known-limitations)

## URL architecture

Eight indexable public URLs exist today, defined once in
`frontend/src/seo/urls.ts` (`allSeoRoutes()` - the single source of truth
used by routing, the sitemap generator, and tests):

```
/en                        /ar
/en/video-downloader       /ar/video-downloader
/en/audio-downloader       /ar/audio-downloader
/en/image-downloader       /ar/image-downloader
```

These are **new, additional** pages - not a replacement for the existing
interactive marketing landing at `/`. `/` keeps working exactly as before
(same hash-anchor navigation to `#features`/`#how-it-works`, same
localStorage-based language toggle, same tests). See "Known limitations"
for why `/` was deliberately left alone in this phase rather than folded
into `/en`/`/ar`.

The rest of the app (`/dashboard`, `/pricing`, `/login`, `/admin`, etc.) is
unchanged and is not part of this bilingual URL set.

## Rendering strategy

Loady's frontend is a client-side Vite + React SPA with no SSR framework
(no Next.js/Remix/Astro). Before this work, every route - including the
public marketing pages - shipped only `<div id="root"></div>`; all content
appeared after the JS bundle executed. That's a real risk for:

- Non-JS-executing crawlers and nearly all social-preview scrapers
  (Slack, Twitter/X, WhatsApp, LinkedIn), which never run JavaScript at all.
- Slower/partial indexing even for engines that do execute JS.

**Decision:** add a small, self-contained **build-time static prerender**
step for just the 8 SEO pages above, rather than migrating the whole app
to an SSR framework (a large, high-risk change the rest of the app,
including auth cookies and the guest-download flow, doesn't need).

How it works (`frontend/scripts/prerender.mjs`, run as the last step of
`npm run build`):

1. `vite build` produces the normal client bundle and `dist/index.html`.
2. The script bundles `frontend/src/entry-server.tsx` with esbuild
   (Node target, JSX enabled) into a throwaway CJS file.
3. For each of the 8 routes, it renders the actual page component
   (`SeoHomePage`/`SeoToolPage` - the *same* components the browser uses,
   routed through real `<Routes>`/`<Route path="/:lang/...">` matching via
   `StaticRouter`) to a markup string with `ReactDOMServer.renderToStaticMarkup`,
   using an isolated SSR-only i18next instance (`src/i18n/ssr.ts` - the
   browser instance touches `localStorage`/`document` at import time, which
   don't exist in Node).
4. The `<Seo>` component (`src/seo/Seo.tsx`) records the page's title/
   description/canonical/hreflang/OG/JSON-LD as a side effect of *rendering*
   (not a `useEffect`, since effects never run during static rendering) into
   a module-level slot the script reads immediately after the render call.
5. The script splices that metadata and the rendered markup into a copy of
   `dist/index.html`, and writes it to `dist/<lang>/<slug>/index.html`.
6. It also writes `dist/sitemap.xml` from the same `allSeoRoutes()` list.

**What a crawler receives**: real `<title>`, meta description, canonical,
hreflang, Open Graph/Twitter tags, JSON-LD, an `<h1>`, and the full visible
page text - all in the initial HTML response, no JavaScript required.

**What a real browser receives**: the same static HTML paints instantly,
then the normal client bundle (`<script type="module" src="/assets/...">`)
loads and boots the SPA as usual. This is *not* React hydration (no
`hydrateRoot`) - the client-side render simply replaces the static markup
with its own live render of the same route. The visual result is
identical (same components, same data), so there's a technical remount but
not a content flash. This tradeoff (prerender for crawlers, plain CSR
takeover for interactivity) was chosen specifically to avoid hydration
mismatch complexity for a handful of largely-static content pages.

Everything else in the app (the authenticated dashboard, admin, billing,
etc.) remains pure client-side rendering - unchanged, and correctly so:
none of that is meant to be indexed (see "Noindex strategy").

## Language architecture

- URL is authoritative for the 8 SEO pages: `useSeoLanguage()`
  (`src/seo/useSeoLanguage.ts`) forces `i18n.changeLanguage(lang)` to match
  the `:lang` URL segment on mount, regardless of any stored preference -
  visiting `/ar/video-downloader` always shows Arabic even if this browser
  last chose English elsewhere on the site.
- This reuses the app's existing global i18next instance and its
  `languageChanged` listener (`src/i18n/index.ts`), so the change also
  updates `document.documentElement.lang/dir` and persists to
  `localStorage` for the rest of the app - identical to what clicking the
  existing `LanguageSwitcher` button already does.
- `SeoLanguageSwitcher` (`src/components/SeoLanguageSwitcher.tsx`) is a
  **real `<Link>`**-based switcher used only on these 8 pages (distinct
  from the app-wide button-based `LanguageSwitcher`), so it works without
  JavaScript for a crawler or no-JS visitor and always lands on a stable,
  indexable sibling URL (`/ar/video-downloader` ↔ `/en/video-downloader`),
  never a same-URL in-place re-render.
- `hreflang` alternates (`hreflangAlternates()` in `urls.ts`) are always
  reciprocal: every language's version of a page links to every other
  language's version of that *same* page, plus `x-default` pointing at the
  English version (matching `fallbackLng: "en"` in `src/i18n/index.ts`).
- Invalid language segments (e.g. `/fr/video-downloader`) render the
  noindexed `NotFoundPage`, not a crash or a silent fallback.

## Canonical strategy

Every SEO page renders exactly one `<link rel="canonical">`, pointing at
its own absolute production URL (`https://loady.cc/<lang>/<slug>`) - never
at the homepage, never at the other language's version. Canonical and
hreflang URLs are always absolute and always point at real, indexable
pages (never a redirect, never a noindexed page).

## Sitemap

Generated at build time (`dist/sitemap.xml`) from the exact same
`allSeoRoutes()` list used for routing and hreflang - it cannot drift from
what was actually built and prerendered. Contains only the 8 URLs above;
no private/app/API path is ever included (enforced by
`src/seo/urls.test.ts`'s "never includes a private/application route" test).

`sitemap.xml` is **not** committed to source - it's build output
(`frontend/dist/` is gitignored), generated fresh on every production build.

## Robots.txt

`frontend/public/robots.txt` (copied verbatim into `dist/` by Vite):

```
User-agent: *
Allow: /
Disallow: /dashboard
Disallow: /history
Disallow: /settings
Disallow: /account
Disallow: /billing
Disallow: /usage
Disallow: /admin
Disallow: /admin/
Disallow: /login
Disallow: /signup
Disallow: /forgot-password
Disallow: /reset-password
Disallow: /verify-email
Disallow: /api/

Sitemap: https://loady.cc/sitemap.xml
```

This is a crawl-budget courtesy, **not** the enforcement mechanism for
either privacy or de-indexing - see the next section.

## Noindex strategy

`robots.txt` `Disallow` stops a crawler from *fetching* a URL, which means
it can never see a `noindex` directive on that page either - a disallowed
but externally-linked URL can still show up indexed with no snippet. The
correct, authoritative mechanism is a live `noindex` meta tag, which
Google's JS-executing crawler does see.

Implemented centrally via `useNoindex()` (`src/seo/useNoindex.ts`), called
from exactly two places so no individual page has to remember to opt out:

1. The three route guards every authenticated/app route already passes
   through - `ProtectedRoute`, `AdminRoute`, `GuestAllowedRoute`
   (`src/components/ProtectedRoute.tsx`). This covers `/dashboard`,
   `/history`, `/settings`, `/account`, `/billing`, `/usage`, `/admin` and
   every admin sub-page, for every account state (including a signed-out
   guest on `/dashboard`).
2. The five standalone, un-guarded auth pages - Login, Signup,
   ForgotPassword, ResetPassword, VerifyEmail - each call `useNoindex()`
   directly, since they aren't behind any of the guards above.

`NotFoundPage` is also noindexed (see "404 / status behavior").

Public/indexable pages (`/`, `/pricing`, `/terms`, `/privacy`,
`/copyright`, and the 8 SEO pages) never call `useNoindex()` and are never
disallowed in `robots.txt`.

## Structured data

Builders live in `src/seo/structuredData.ts` and only encode facts already
visible on the page they're attached to:

- **WebSite** (home page only) - name and URL.
- **SoftwareApplication** (every page) - name, category, URL. No price,
  no rating, no review count - none of that exists to report truthfully.
- **BreadcrumbList** (tool pages) - Home → this tool, matching the visible
  breadcrumb nav.
- **FAQPage** (tool pages) - built directly from the same FAQ array
  rendered as visible `<details>` elements on the page; never hidden or
  divorced from what a visitor actually sees.

No ratings, review counts, prices, awards, or platform-support claims are
fabricated anywhere.

## Production base URL configuration

Canonical/hreflang/OG/sitemap URLs use a fixed production origin
(`PRODUCTION_ORIGIN = "https://loady.cc"` in `src/seo/urls.ts`), not
`window.location.origin` - these tags are only meaningful once deployed, so
a local dev server never leaks `http://127.0.0.1:5173` into them.

To point a staging build at a different domain, set `VITE_SITE_URL` at
build time (e.g. `VITE_SITE_URL=https://staging.loady.cc npm run build`);
leave it unset for production (`loady.cc`) and for local development
(local dev never renders these tags into anything user-facing anyway).

## Verifying the prerendered output

After `npm run build`, inspect the actual static files a crawler would
receive:

```sh
cd frontend
npm run build
grep -A2 '<title>' dist/en/video-downloader/index.html
grep 'rel="canonical"\|hreflang' dist/ar/audio-downloader/index.html
cat dist/sitemap.xml
cat dist/robots.txt
```

Each `dist/<lang>/<slug>/index.html` is a complete, real HTML document -
open it directly in a browser with JavaScript disabled to confirm content
is visible without it.

## Search Console setup (after loady.cc is live)

Cannot be done from local development - no verification token is invented
or stored in this repo. Once deployed:

1. Deploy `loady.cc` and confirm HTTPS is valid.
2. Manually verify canonical URLs resolve correctly in a browser
   (`https://loady.cc/en`, `https://loady.cc/ar`, etc.).
3. Verify `https://loady.cc/robots.txt` is reachable and correct.
4. Verify `https://loady.cc/sitemap.xml` is reachable and lists exactly
   the 8 URLs above.
5. Add `loady.cc` as a property in
   [Google Search Console](https://search.google.com/search-console).
6. Verify ownership (DNS TXT record recommended - no token belongs in
   source control; a meta-tag verification token, if used instead, should
   be added directly to `frontend/index.html`'s `<head>` at deploy time,
   not committed speculatively here).
7. Submit `sitemap.xml` in Search Console.
8. Use URL Inspection on `/en` and `/ar` to confirm Google can render them.
9. Request indexing for the primary pages (`/en`, `/ar`, and the three
   tool pages in each language).
10. Monitor the Coverage/Indexing report over the following days.
11. Monitor Core Web Vitals in Search Console / PageSpeed Insights.
12. Monitor Performance → Queries, filtered separately by page/country for
    English vs. Arabic traffic - they behave as genuinely different
    audiences and shouldn't be read as one blended number.

## Analytics readiness

No analytics provider is wired up in this codebase (`src/lib/analytics.ts`
only logs to the dev console). This phase does not add one - introducing a
third-party analytics vendor is a separate decision requiring explicit
approval, not something to bundle into an SEO pass.

Documented for when that decision is made: extend the existing
`AnalyticsEvent` union in `src/lib/analytics.ts` with SEO-relevant events
such as `seo_page_view`, `seo_tool_cta_clicked`, or
`seo_language_switched`, and call `track(...)` from the SEO pages the same
way `Dashboard.tsx`/`Pricing.tsx` already do. Keep it non-invasive: no
cross-site tracking, no PII, consistent with the existing privacy note at
the top of `analytics.ts`.

## Content-quality rules

- No keyword stuffing, no repeated exact-match phrases, no "best
  downloader"/"100% safe"/"works everywhere" claims.
- Every claim on a tool page must match what the backend actually does -
  see `app/utils/url_detect.py` (supported platforms: YouTube, TikTok,
  Instagram, Facebook) and `app/services/download_manager.py`
  (Compatibility MP4 vs Original container, MP3/M4A audio, image/carousel
  support) before writing or editing copy.
- Arabic content is written as natural Modern Standard Arabic for a
  GCC/wider Arabic-speaking audience, not a literal machine translation -
  technical terms that Arabic-speaking users commonly encounter in English
  (MP4, MP3, URL, HD, 4K) are kept as-is rather than forced into an
  unfamiliar Arabic equivalent.
- Responsible-use language only ("content you own or are otherwise
  authorized to save") - never wording that encourages bypassing DRM,
  access restrictions, or platform terms.

## How to add a new bilingual SEO page

1. Confirm a real user/search intent exists (not just "more pages").
2. Write meaningful, original English content - grounded only in what the
   product actually does (see "Content-quality rules").
3. Write a genuine Arabic localization (not a literal translation) once
   the English content is settled.
4. Add the page's key to `SeoPageKey`/`SEO_PAGE_SLUGS`/`SEO_PAGES` in
   `frontend/src/seo/urls.ts` - this alone gets it into `allSeoRoutes()`
   (sitemap, hreflang, tests) automatically.
5. Add its content under a new `seo.<page>` block in both
   `frontend/src/i18n/locales/en.json` and `ar.json`, plus
   `seo.meta.<page>.{title,description}`.
6. Build the page component under `frontend/src/pages/seo/` (reuse
   `SeoToolPage.tsx`'s template if the new page is another "tool" page
   with the same intro/about/steps/FAQ shape; otherwise write a new
   component following `SeoHomePage.tsx`'s pattern - always rendering a
   `<Seo>` with `url`, `title`, `description`, and `hreflang`).
7. Add its route(s) to `AppShell`'s `<Routes>` in `frontend/src/App.tsx`
   **and** to the mirrored `<Routes>` in `frontend/src/entry-server.tsx`
   (the prerender script renders through that second route table, not
   `App.tsx`, since App.tsx also pulls in the entire authenticated app).
8. Add truthful structured data via `src/seo/structuredData.ts` only if it
   matches content genuinely visible on the new page.
9. Add internal links to and from the new page (home → new page, new page
   → related tools) using real `<Link>`s.
10. Add tests: a `urls.test.ts`-style route assertion, a page-render test
    (H1, lang/dir, canonical, hreflang) mirroring
    `SeoHomePage.test.tsx`/`SeoToolPage.test.tsx`, and a Playwright check
    in `e2e/seo.spec.ts`.
11. Run `npm run build` and inspect the new `dist/<lang>/<slug>/index.html`
    directly (see "Verifying the prerendered output") before shipping.

## 404 / status behavior

`NotFoundPage` (`src/pages/NotFoundPage.tsx`) renders for any unmatched
route (React Router's `path="*"` catch-all in `App.tsx`) and for an
invalid `:lang` segment on the SEO routes (e.g. `/fr/video-downloader`).
It's noindexed, shows a helpful message, and links back to `/`.

This is a **best-effort client-side signal only**. A pure SPA fallback is
served as an HTTP **200** by essentially every static host by default
(the same file - `index.html` - is returned for any unmatched path so the
client router can take over), which is not a genuine HTTP 404. Getting a
real 404 status for unknown paths requires production host configuration
that this repository does not currently define (there's no committed
Dockerfile/nginx config/Vercel config yet):

- **nginx** (or any server serving `dist/` directly): the prerendered SEO
  pages are real files, so `try_files $uri $uri/ /index.html;` correctly
  serves them as-is; genuinely unknown paths fall through to
  `/index.html` (still 200, client renders the noindexed 404 page) unless
  you add a dedicated `error_page 404 /404.html;` with a static
  `404.html` returned via `return 404;`.
- **Vercel**: a `vercel.json` rewrite of unmatched paths to `/index.html`
  gets the same 200-with-client-404-page behavior; a true 404 status needs
  an explicit `"status": 404` route for a dedicated 404 page instead of a
  blanket SPA rewrite.
- **Netlify**: equivalent tradeoff via `_redirects`/`netlify.toml` - a
  bare SPA fallback rule is 200; add a specific 404 page rule for a real
  status code.

Whichever host is chosen at deploy time, this tradeoff should be resolved
then, with the actual hosting config committed alongside it.

## Known limitations

- **`/` is intentionally unchanged.** The interactive marketing landing at
  `/` (hash-anchor nav to `#features`/`#how-it-works`, localStorage-based
  language toggle) predates this work and has real existing test coverage
  (`e2e/route-scroll.spec.ts`, `e2e/i18n.spec.ts`) plus real inbound value
  as a page. Consolidating it into `/en`/`/ar` (so the root domain itself
  redirects to a locale) would require rewriting `Header`/`Footer`'s
  hardcoded `/#features`/`/#how-it-works` links, `HashScroll`'s behavior,
  and the existing tests that depend on exact `/` behavior - a larger,
  separate migration this phase deliberately did not take on, to honor the
  explicit constraint not to break the existing landing page, its nav, or
  its scroll behavior. See "Recommended Phase 2 priorities" in the final
  report.
- **No true HTTP 404** without production host configuration (see above) -
  this repo has no committed hosting config to attach it to yet.
- **Clearing `localStorage` resets a returning visitor's language choice**
  outside the 8 SEO pages (the rest of the app was already localStorage-
  based before this work; the SEO pages fix this specifically by making
  the URL authoritative, per Section 3's requirement).
- **No Search Console verification token is stored anywhere in this repo**
  - by design; add it at actual deploy time (see "Search Console setup").
- **No analytics provider is wired up** - documented as ready-to-extend,
  not implemented, since adding one is a separate decision.
