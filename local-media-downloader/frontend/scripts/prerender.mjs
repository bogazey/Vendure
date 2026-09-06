#!/usr/bin/env node
/**
 * Build-time static rendering for the bilingual SEO pages (/en, /ar, and
 * their tool sub-pages). Runs after `vite build` (see package.json's
 * "build" script) so crawlers and social-preview scrapers get real HTML -
 * title, description, canonical, hreflang, Open Graph, and JSON-LD - for
 * these specific public pages without executing JavaScript. Everything
 * else in the app stays a normal client-side SPA; see docs/SEO.md
 * "Rendering strategy" for the reasoning and tradeoffs.
 *
 * Also generates dist/sitemap.xml from the same route list used here, so
 * the sitemap can never drift from what was actually prerendered.
 */
import { build } from "esbuild";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "dist");
const TMP_DIR = path.join(ROOT, "node_modules", ".prerender-tmp");
const BUNDLE_PATH = path.join(TMP_DIR, "entry-server.cjs");

async function bundleEntryServer() {
  await mkdir(TMP_DIR, { recursive: true });
  await build({
    entryPoints: [path.join(ROOT, "src", "entry-server.tsx")],
    bundle: true,
    platform: "node",
    format: "cjs",
    target: "node18",
    jsx: "automatic",
    outfile: BUNDLE_PATH,
    // Every dependency the SSR entry actually touches (react, react-dom,
    // react-router-dom, i18next, react-i18next) ships a Node-resolvable
    // CJS entry point, so there's no need to bundle them - just the app's
    // own source (page components, seo/, i18n/locales JSON).
    external: ["react", "react-dom", "react-dom/server", "react-router-dom", "react-router-dom/server", "react-i18next", "i18next"],
    define: {
      "import.meta.env.VITE_SITE_URL": JSON.stringify(process.env.VITE_SITE_URL ?? ""),
    },
    logLevel: "silent",
  });
}

function escapeHtml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildHeadExtras(seo) {
  const tags = [];
  tags.push(`<title>${escapeHtml(seo.title)}</title>`);
  tags.push(`<meta name="description" content="${escapeHtml(seo.description)}" />`);
  tags.push(`<link rel="canonical" href="${escapeHtml(seo.url)}" />`);
  tags.push(`<meta property="og:title" content="${escapeHtml(seo.ogTitle ?? seo.title)}" />`);
  tags.push(`<meta property="og:description" content="${escapeHtml(seo.ogDescription ?? seo.description)}" />`);
  tags.push(`<meta property="og:url" content="${escapeHtml(seo.url)}" />`);
  tags.push(`<meta property="og:type" content="website" />`);
  if (seo.ogImage) tags.push(`<meta property="og:image" content="${escapeHtml(seo.ogImage)}" />`);
  tags.push(`<meta name="twitter:card" content="${seo.ogImage ? "summary_large_image" : "summary"}" />`);
  for (const alt of seo.hreflang ?? []) {
    tags.push(`<link rel="alternate" hreflang="${alt.hreflang}" href="${escapeHtml(alt.href)}" />`);
  }
  if (seo.noindex) tags.push(`<meta name="robots" content="noindex, nofollow" />`);
  const structuredData = Array.isArray(seo.structuredData) ? seo.structuredData : seo.structuredData ? [seo.structuredData] : [];
  for (const data of structuredData) {
    tags.push(`<script type="application/ld+json">${JSON.stringify(data)}</script>`);
  }
  return tags.join("\n    ");
}

function applyToTemplate(template, lang, headExtras, bodyHtml) {
  let html = template;
  // The base template already carries a default <title> and
  // meta[name="description"] (see index.html) - drop them so the page-
  // specific ones injected above are the only ones a crawler sees.
  html = html.replace(/<title>.*?<\/title>/s, "");
  html = html.replace(/<meta\s+name="description"[^>]*>/, "");
  html = html.replace(/<meta property="og:title"[^>]*>/, "");
  html = html.replace(/<meta\s+property="og:description"[^>]*>/, "");
  html = html.replace(/<meta property="og:type"[^>]*>/, "");
  html = html.replace(/<html lang="en"([^>]*)>/, (_match, rest) => {
    const withoutDir = rest.replace(/\s*dir="[^"]*"/, "");
    return `<html lang="${lang}"${withoutDir} dir="${lang === "ar" ? "rtl" : "ltr"}">`;
  });
  html = html.replace("</head>", `    ${headExtras}\n  </head>`);
  html = html.replace('<div id="root"></div>', `<div id="root">${bodyHtml}</div>`);
  return html;
}

function buildSitemap(routes) {
  const urls = routes
    .map((route) => `  <url>\n    <loc>${escapeHtml(route.url)}</loc>\n  </url>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

async function main() {
  await bundleEntryServer();
  delete require.cache[BUNDLE_PATH];
  const { renderSeoRoute, allSeoRoutes } = require(BUNDLE_PATH);

  const template = await readFile(path.join(DIST, "index.html"), "utf-8");
  const routes = allSeoRoutes();

  for (const route of routes) {
    const { bodyHtml, seo } = await renderSeoRoute(route.lang, route.page, route.path);
    if (!seo) {
      throw new Error(`Prerender produced no SEO metadata for ${route.path} - Seo component did not render.`);
    }
    const headExtras = buildHeadExtras(seo);
    const html = applyToTemplate(template, route.lang, headExtras, bodyHtml);

    const outDir = path.join(DIST, route.path.replace(/^\//, ""));
    await mkdir(outDir, { recursive: true });
    await writeFile(path.join(outDir, "index.html"), html, "utf-8");
    console.log(`Prerendered ${route.path} -> ${path.relative(ROOT, path.join(outDir, "index.html"))}`);
  }

  const sitemap = buildSitemap(routes);
  await writeFile(path.join(DIST, "sitemap.xml"), sitemap, "utf-8");
  console.log(`Wrote sitemap.xml with ${routes.length} URLs`);

  await rm(TMP_DIR, { recursive: true, force: true });
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
