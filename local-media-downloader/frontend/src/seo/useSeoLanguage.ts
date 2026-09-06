import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { isSeoLanguage, type SeoLanguage } from "./urls";

/**
 * Resolves and enforces the language for a /:lang SEO route. The URL is
 * authoritative here - unlike the rest of the app (which only ever
 * changes language via the LanguageSwitcher button, persisted to
 * localStorage), visiting /ar/video-downloader must show Arabic even if
 * this browser's stored preference is still "en", and vice versa. This
 * mirrors what LanguageSwitcher already does (i18n.changeLanguage), so it
 * also updates localStorage and document lang/dir for the rest of the app
 * via the existing i18n "languageChanged" listener - see src/i18n/index.ts.
 */
export function useSeoLanguage(langParam: string | undefined): { lang: SeoLanguage | null } {
  const { i18n } = useTranslation();
  const lang = isSeoLanguage(langParam) ? langParam : null;

  useEffect(() => {
    if (lang && i18n.resolvedLanguage !== lang) {
      void i18n.changeLanguage(lang);
    }
  }, [lang, i18n]);

  return { lang };
}
