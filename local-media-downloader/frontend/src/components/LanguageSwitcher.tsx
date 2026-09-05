import { useTranslation } from "react-i18next";

export default function LanguageSwitcher({ mobile = false }: { mobile?: boolean }) {
  const { i18n, t } = useTranslation();
  const language = i18n.resolvedLanguage === "ar" ? "ar" : "en";

  return (
    <div
      className={mobile ? "mt-2 flex items-center justify-between border-t border-white/[0.08] pt-3" : "flex items-center rounded-xl border border-white/[0.08] bg-white/[0.025] p-1"}
      role="group"
      aria-label={t("language.label")}
    >
      {mobile && <span className="text-xs font-medium text-slate-500">{t("language.label")}</span>}
      <div className="flex items-center gap-0.5" dir="ltr">
        {(["en", "ar"] as const).map((code) => (
          <button
            key={code}
            type="button"
            onClick={() => void i18n.changeLanguage(code)}
            aria-pressed={language === code}
            className={`rounded-lg px-2 py-1 text-[11px] font-semibold transition-colors ${language === code ? "bg-white/[0.09] text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
          >
            {code === "en" ? t("language.english") : t("language.arabic")}
          </button>
        ))}
      </div>
    </div>
  );
}
