import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { seoPath, type SeoLanguage, type SeoPageKey } from "../seo/urls";

/**
 * Language switcher for the bilingual SEO pages - real <Link> anchors to
 * the sibling-language URL of the same page (not a JS-only button that
 * calls i18n.changeLanguage in place, like the app-wide LanguageSwitcher).
 * A real href means it works for a crawler or a no-JS visitor reading the
 * prerendered HTML, and it lands on a stable, indexable URL rather than
 * silently re-rendering the same page in another language.
 */
export default function SeoLanguageSwitcher({ page, current }: { page: SeoPageKey; current: SeoLanguage }) {
  const { t } = useTranslation();
  const options: SeoLanguage[] = ["en", "ar"];

  return (
    <div
      className="flex items-center gap-0.5 rounded-xl border border-white/[0.08] bg-white/[0.025] p-1"
      role="group"
      aria-label={t("language.label")}
      dir="ltr"
    >
      {options.map((lang) => (
        <Link
          key={lang}
          to={seoPath(lang, page)}
          aria-current={lang === current ? "page" : undefined}
          className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors ${
            lang === current ? "bg-white/[0.09] text-slate-100" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {lang === "en" ? t("language.english") : t("language.arabic")}
        </Link>
      ))}
    </div>
  );
}
