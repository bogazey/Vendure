import { useParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Seo } from "../../seo/Seo";
import { hreflangAlternates, seoPath, seoUrl, type SeoPageKey } from "../../seo/urls";
import { breadcrumbStructuredData, faqStructuredData, softwareApplicationStructuredData } from "../../seo/structuredData";
import { useSeoLanguage } from "../../seo/useSeoLanguage";
import SeoLanguageSwitcher from "../../components/SeoLanguageSwitcher";
import NotFoundPage from "../NotFoundPage";

interface FaqEntry {
  q: string;
  a: string;
}

interface StepEntry {
  title: string;
  body: string;
}

const OTHER_TOOLS: Record<Exclude<SeoPageKey, "home">, Exclude<SeoPageKey, "home">[]> = {
  video: ["audio", "image"],
  audio: ["video", "image"],
  image: ["video", "audio"],
};

/**
 * Shared template for the three tool pages (video/audio/image) - the same
 * layout with per-page content pulled from seo.<page>.* and seo.meta.<page>.*
 * in the locale files. Sharing a template is a code-reuse choice, not a
 * content shortcut: each page's actual text, FAQ, and metadata are unique
 * and genuinely describe that page's capability (see docs/SEO.md).
 */
export default function SeoToolPage({ page }: { page: Exclude<SeoPageKey, "home"> }) {
  const { lang: langParam } = useParams<{ lang: string }>();
  const { lang } = useSeoLanguage(langParam);
  const { t } = useTranslation();

  if (!lang) return <NotFoundPage />;

  const faq = t(`seo.${page}.faq`, { returnObjects: true }) as FaqEntry[];
  const steps = t(`seo.${page}.steps`, { returnObjects: true }) as StepEntry[];
  const homeUrl = seoUrl(lang, "home");
  const pageUrl = seoUrl(lang, page);

  return (
    <main className="landing-page">
      <Seo
        url={pageUrl}
        title={t(`seo.meta.${page}.title`)}
        description={t(`seo.meta.${page}.description`)}
        lang={lang}
        hreflang={hreflangAlternates(page)}
        ogImage="https://loady.cc/assets/brand/loady-og.png?v=db4ff8097b78"
        structuredData={[
          softwareApplicationStructuredData(),
          breadcrumbStructuredData([
            { name: t("seo.common.home"), url: homeUrl },
            { name: t(`seo.common.${page}Tool`), url: pageUrl },
          ]),
          faqStructuredData(faq.map((item) => ({ question: item.q, answer: item.a }))),
        ]}
      />

      <section className="section-shell">
        <nav aria-label="Breadcrumb" className="mb-4 flex items-center justify-center gap-2 text-xs text-slate-500">
          <Link to={seoPath(lang, "home")} className="hover:text-slate-300">{t("seo.common.home")}</Link>
          <span aria-hidden="true">/</span>
          <span className="text-slate-400">{t(`seo.common.${page}Tool`)}</span>
        </nav>
        <div className="mb-6 flex justify-center">
          <SeoLanguageSwitcher page={page} current={lang} />
        </div>
        <div className="section-intro">
          <h1>{t(`seo.${page}.h1`)}</h1>
          <p>{t(`seo.${page}.intro`)}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link to="/dashboard" className="btn-gradient !px-7 !py-3.5">
            {t("seo.common.tryNowCta")}
          </Link>
        </div>
        <p className="mt-4 text-center text-sm text-slate-500">{t("seo.common.guestNote")}</p>
      </section>

      <section className="section-shell">
        <div className="section-intro">
          <h2>{t(`seo.${page}.aboutTitle`)}</h2>
          <p>{t(`seo.${page}.aboutBody`)}</p>
        </div>
        <div className="glass-panel-raised mx-auto max-w-3xl p-6">
          <h3 className="font-display text-lg font-semibold text-slate-50">{t(`seo.${page}.qualityTitle`)}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-400">{t(`seo.${page}.qualityBody`)}</p>
        </div>
      </section>

      <section className="section-shell how-section">
        <div className="section-intro">
          <span className="section-kicker">{t("seo.common.usageTitle")}</span>
        </div>
        <div className="step-path">
          {steps.map((step, i) => (
            <article key={step.title} className="step-card">
              <div className="step-top"><span className="step-number">0{i + 1}</span></div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <div className="section-intro">
          <h2>{t("seo.common.faqTitle")}</h2>
        </div>
        <div className="mx-auto flex max-w-2xl flex-col gap-3">
          {faq.map((item) => (
            <details key={item.q} className="glass-panel rounded-2xl p-4">
              <summary className="cursor-pointer font-medium text-slate-100">{item.q}</summary>
              <p className="mt-2 text-sm leading-6 text-slate-400">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="section-shell">
        <div className="section-intro">
          <span className="section-kicker">{t("seo.common.relatedTools")}</span>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-3">
          {OTHER_TOOLS[page].map((other) => (
            <Link key={other} to={seoPath(lang, other)} className="btn-glass !px-6 !py-3">
              {t(`seo.common.${other}Tool`)}
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
