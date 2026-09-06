/**
 * Build-time-only SSR entry (Node, never shipped to the browser) - bundled
 * and executed by scripts/prerender.mjs after `vite build`. Renders each
 * bilingual SEO page to static markup so crawlers and social-preview
 * scrapers get real HTML without executing JavaScript. See docs/SEO.md,
 * "Rendering strategy".
 */
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { Route, Routes } from "react-router-dom";
import { StaticRouter } from "react-router-dom/server";
import ssrI18n from "./i18n/ssr";
import { lastRenderedSeo, type SeoProps } from "./seo/Seo";
import { allSeoRoutes, type SeoLanguage, type SeoPageKey } from "./seo/urls";
import SeoHomePage from "./pages/seo/SeoHomePage";
import SeoToolPage from "./pages/seo/SeoToolPage";

export { allSeoRoutes };

function SeoRoutesForPrerender() {
  return (
    <Routes>
      <Route path="/:lang" element={<SeoHomePage />} />
      <Route path="/:lang/video-downloader" element={<SeoToolPage page="video" />} />
      <Route path="/:lang/audio-downloader" element={<SeoToolPage page="audio" />} />
      <Route path="/:lang/image-downloader" element={<SeoToolPage page="image" />} />
    </Routes>
  );
}

export interface RenderedSeoRoute {
  bodyHtml: string;
  seo: SeoProps | null;
}

export async function renderSeoRoute(lang: SeoLanguage, _page: SeoPageKey, path: string): Promise<RenderedSeoRoute> {
  await ssrI18n.changeLanguage(lang);
  const bodyHtml = renderToStaticMarkup(
    <I18nextProvider i18n={ssrI18n}>
      <StaticRouter location={path}>
        <SeoRoutesForPrerender />
      </StaticRouter>
    </I18nextProvider>,
  );
  return { bodyHtml, seo: lastRenderedSeo };
}
