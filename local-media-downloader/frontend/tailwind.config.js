/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "var(--color-surface)",
          raised: "var(--color-surface-raised)",
          border: "var(--color-surface-border)",
        },
        // Only the shades actually used across the app are re-pointed at CSS
        // vars; unlisted shades (700-950) fall back to Tailwind's defaults
        // via the deep merge that `extend` performs.
        slate: {
          50: "var(--color-slate-50)",
          100: "var(--color-slate-100)",
          200: "var(--color-slate-200)",
          300: "var(--color-slate-300)",
          400: "var(--color-slate-400)",
          500: "var(--color-slate-500)",
          600: "var(--color-slate-600)",
        },
        // Loady Brand Identity #2's official palette - exact hex values from
        // design-reference/brand-kit/README.md + guidelines PDF +
        // web/loady-tokens.css (all three agree). "purple" here is the
        // kit's "Violet" token; named to match the existing blue/purple/aqua
        // vocabulary used throughout the app's classNames.
        brand: {
          blue: "#3B82F6",
          purple: "#8B5CF6",
          aqua: "#22D3EE",
        },
      },
      backgroundImage: {
        // Official primary gradient, verbatim: 135deg, aqua -> blue -> violet.
        "brand-gradient": "linear-gradient(135deg, #22D3EE 0%, #3B82F6 55%, #8B5CF6 100%)",
        "brand-gradient-soft": "linear-gradient(135deg, rgba(34,211,238,0.16) 0%, rgba(59,130,246,0.18) 50%, rgba(139,92,246,0.16) 100%)",
        "brand-radial-1": "radial-gradient(closest-side, rgba(59,130,246,0.5), transparent)",
        "brand-radial-2": "radial-gradient(closest-side, rgba(139,92,246,0.45), transparent)",
        "brand-radial-3": "radial-gradient(closest-side, rgba(34,211,238,0.38), transparent)",
      },
      boxShadow: {
        // "glow"/"glow-lg" are used directly as `shadow-glow`/`shadow-glow-lg`
        // classNames in JSX (Tailwind's normal content-scanned JIT path).
        // The equivalent glass-panel/btn-gradient shadows are hardcoded as
        // plain CSS in index.css instead of a custom key applied via
        // `@apply` - see the comments there for why.
        glow: "0 0 0 1px rgba(139,92,246,0.15), 0 8px 30px -6px rgba(59,130,246,0.35), 0 2px 12px -2px rgba(34,211,238,0.2)",
        "glow-lg": "0 0 0 1px rgba(139,92,246,0.18), 0 20px 60px -12px rgba(59,130,246,0.45), 0 8px 30px -8px rgba(139,92,246,0.3)",
      },
      fontFamily: {
        // Sora is Brand Identity #2's official typeface (both headings and
        // body, per the guidelines PDF's weight table); Inter/system-ui are
        // the kit's own specified fallback, not a deliberate second voice.
        sans: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      animation: {
        "aurora-drift-1": "auroraDrift1 26s ease-in-out infinite",
        "aurora-drift-2": "auroraDrift2 32s ease-in-out infinite",
        "aurora-drift-3": "auroraDrift3 22s ease-in-out infinite",
      },
      keyframes: {
        auroraDrift1: {
          "0%, 100%": { transform: "translate(-5%, -8%) scale(1)" },
          "50%": { transform: "translate(6%, 4%) scale(1.12)" },
        },
        auroraDrift2: {
          "0%, 100%": { transform: "translate(4%, 6%) scale(1.05)" },
          "50%": { transform: "translate(-6%, -4%) scale(0.95)" },
        },
        auroraDrift3: {
          "0%, 100%": { transform: "translate(0%, 0%) scale(1)" },
          "50%": { transform: "translate(-4%, 5%) scale(1.08)" },
        },
      },
    },
  },
  plugins: [],
};
