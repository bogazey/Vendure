/**
 * Shared Loady surface/typography tokens as plain class-string constants -
 * the same pattern the auth pages already used (see the old formStyles.ts,
 * now superseded by this file), generalized to the whole app so every
 * page draws from one definition of "glass panel," "primary button," etc.
 * Prefer these over inventing new ad-hoc utility chains per component.
 */

// Panels
export const glassPanel = "glass-panel";
export const glassPanelRaised = "glass-panel-raised";

// Buttons
export const primaryButton = "btn-gradient";
export const secondaryButton = "btn-glass";
export const dangerGhostButton =
  "inline-flex items-center justify-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/5 px-4 py-2.5 text-sm font-medium text-red-300 transition-colors hover:border-red-500/40 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-50";

// Inputs
export const glassInput = "input-glass";

// Typography
export const pageHeading = "font-display text-2xl font-bold tracking-tight text-slate-50 sm:text-3xl";
export const sectionHeading = "font-display text-lg font-semibold tracking-tight text-slate-50";
export const eyebrow = "text-xs font-semibold uppercase tracking-[0.14em] text-brand-aqua/90";
export const mutedText = "text-sm text-slate-400";
export const gradientText = "gradient-text";
export const brandLink = "font-medium text-brand-aqua transition-colors hover:text-brand-purple";

// Badges
export const pillBase = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium";
export const planBadge = "rounded-full bg-brand-gradient px-2.5 py-0.5 text-xs font-semibold text-white shadow-glow";

// Layout
export const pageShell = "relative z-10 mx-auto flex w-full flex-col gap-8 px-6 py-10";
export const narrowShell = `${pageShell} max-w-lg`;
export const mediumShell = `${pageShell} max-w-3xl`;
export const wideShell = `${pageShell} max-w-6xl`;

/**
 * One shared container for every authenticated app-shell page (Dashboard,
 * My Downloads, Account, Settings, Billing) - a single consistent
 * max-width/gutter so content reads as deliberately positioned next to the
 * Sidebar rather than centered in whatever empty canvas is left over.
 */
export const appPageShell =
  "relative z-10 mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-8 sm:px-8 lg:px-10 lg:py-10";
