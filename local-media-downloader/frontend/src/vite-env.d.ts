/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Production origin used to build absolute canonical/hreflang/OG URLs -
   * see src/seo/urls.ts. Never read at runtime for anything other than SEO
   * tag generation, so a missing value in local dev is harmless. */
  readonly VITE_SITE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
