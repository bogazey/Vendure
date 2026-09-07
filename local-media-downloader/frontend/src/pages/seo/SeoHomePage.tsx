import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Seo } from "../../seo/Seo";
import { hreflangAlternates, seoPath, seoUrl } from "../../seo/urls";
import { websiteStructuredData, softwareApplicationStructuredData } from "../../seo/structuredData";
import { useSeoLanguage } from "../../seo/useSeoLanguage";
import SeoLanguageSwitcher from "../../components/SeoLanguageSwitcher";
import NotFoundPage from "../NotFoundPage";

const TOOLS = ["video", "audio", "image"] as const;

/**
 * The bilingual, indexable homepage at /en and /ar - distinct from the
 * interactive app landing at "/" (see docs/SEO.md for why both exist).
 * Genuinely original copy and a real internal-linking structure to the
 * three tool pages, not a thin duplicate of the app landing page.
 */
export default function SeoHomePage() {
  const { lang: langParam } = useParams<{ lang: string }>();
  const { lang } = useSeoLanguage(langParam);
  const { t } = useTranslation();

  if (!lang) return <NotFoundPage />;

  return (
    <main className="landing-page">
      <Seo
        url={seoUrl(lang, "home")}
        title={t("seo.meta.home.title")}
        description={t("seo.meta.home.description")}
        lang={lang}
        hreflang={hreflangAlternates("home")}
        ogImage="https://loady.cc/assets/brand/loady-og.png?v=db4ff8097b78"
        structuredData={[websiteStructuredData(), softwareApplicationStructuredData()]}
      />

      <section className="section-shell">
        <div className="mb-6 flex justify-center">
          <SeoLanguageSwitcher page="home" current={lang} />
        </div>
        <div className="section-intro">
          <h1>{t("seo.home.h1")}</h1>
          <p>{t("seo.home.intro")}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link to="/dashboard" className="btn-gradient !px-7 !py-3.5">
            {t("seo.common.tryNowCta")}
          </Link>
          <Link to="/signup" className="btn-glass !px-7 !py-3.5">
            {t("seo.common.signupCta")}
          </Link>
        </div>
        <p className="mt-4 text-center text-sm text-slate-500">{t("seo.common.guestNote")}</p>
      </section>

      <section className="section-shell">
        <div className="section-intro">
          <span className="section-kicker">{t("seo.home.toolsKicker")}</span>
          <h2>{t("seo.home.toolsTitle")}</h2>
        </div>
        <div className="feature-grid">
          {TOOLS.map((tool, i) => (
            <article key={tool} className={`feature-card feature-${["blue", "aqua", "purple"][i]}`}>
              <span className="feature-index">0{i + 1}</span>
              <h3>{t(`seo.home.tools.${tool}.title`)}</h3>
              <p>{t(`seo.home.tools.${tool}.body`)}</p>
              <Link to={seoPath(lang, tool)} className="mt-4 inline-block text-sm font-medium text-brand-aqua transition-colors hover:text-brand-purple">
                {t(`seo.common.${tool}Tool`)} →
              </Link>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
