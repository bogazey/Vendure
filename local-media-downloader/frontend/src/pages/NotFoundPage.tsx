import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Seo } from "../seo/Seo";
import { siteOrigin } from "../seo/urls";

/**
 * Client-side 404 for any unmatched route (and for an invalid :lang
 * segment on the SEO pages, e.g. /fr/video-downloader). This is a
 * best-effort SEO signal only - a genuine HTTP 404 status for unknown
 * paths requires the production static host to be configured for it (see
 * docs/SEO.md, "404 / status behavior"), since a pure client-side SPA
 * fallback is served as HTTP 200 by default on most static hosts.
 */
export default function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <main className="section-shell text-center">
      <Seo
        url={`${siteOrigin()}/404`}
        title={t("seo.common.notFoundTitle")}
        description={t("seo.common.notFoundBody")}
        noindex
      />
      <div className="section-intro">
        <h1>{t("seo.common.notFoundTitle")}</h1>
        <p>{t("seo.common.notFoundBody")}</p>
      </div>
      <Link to="/" className="btn-gradient !px-7 !py-3.5">
        {t("seo.common.notFoundCta")}
      </Link>
    </main>
  );
}
