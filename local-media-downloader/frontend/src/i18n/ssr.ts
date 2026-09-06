/**
 * A second, isolated i18next instance used ONLY by entry-server.tsx's
 * build-time static rendering (scripts/prerender.mjs). The browser i18n
 * instance (./index.ts) touches `localStorage` and `document` at module
 * load time, which don't exist in the Node prerender process - rather
 * than stub those globals, this keeps SSR i18n entirely separate so
 * neither runtime has to know about the other.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

const ssrI18n = i18n.createInstance();
void ssrI18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: "en",
  fallbackLng: "en",
  supportedLngs: ["en", "ar"],
  interpolation: { escapeValue: false },
});

export default ssrI18n;
