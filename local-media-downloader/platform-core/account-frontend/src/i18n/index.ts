import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

export type SupportedLanguage = "en" | "ar";
const LANGUAGE_STORAGE_KEY = "account-portal-language";

let saved: string | null = null;
try {
  saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
} catch {
  saved = null;
}
const initialLanguage: SupportedLanguage = saved === "ar" ? "ar" : "en";

function applyDocumentLanguage(language: string) {
  const resolved: SupportedLanguage = language.startsWith("ar") ? "ar" : "en";
  document.documentElement.lang = resolved;
  document.documentElement.dir = resolved === "ar" ? "rtl" : "ltr";
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, resolved);
  } catch {
    /* private browsing / storage blocked - not fatal */
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: initialLanguage,
  fallbackLng: "en",
  supportedLngs: ["en", "ar"],
  interpolation: { escapeValue: false },
});

applyDocumentLanguage(initialLanguage);
i18n.on("languageChanged", applyDocumentLanguage);

export default i18n;
