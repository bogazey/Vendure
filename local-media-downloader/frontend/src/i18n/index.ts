import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

export const LANGUAGE_STORAGE_KEY = "loady-language";
export type SupportedLanguage = "en" | "ar";

const savedLanguage = localStorage.getItem(LANGUAGE_STORAGE_KEY);
const initialLanguage: SupportedLanguage = savedLanguage === "ar" ? "ar" : "en";

function applyDocumentLanguage(language: string) {
  const resolved: SupportedLanguage = language.startsWith("ar") ? "ar" : "en";
  document.documentElement.lang = resolved;
  document.documentElement.dir = resolved === "ar" ? "rtl" : "ltr";
  localStorage.setItem(LANGUAGE_STORAGE_KEY, resolved);
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
