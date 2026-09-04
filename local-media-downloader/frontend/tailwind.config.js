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
        // Loady brand gradient stops - blue -> purple -> aqua. Named
        // "brand" rather than reusing indigo/violet/cyan so every gradient
        // in the app traces back to one deliberate palette.
        brand: {
          blue: "#4F7CFF",
          purple: "#9D5CFF",
          aqua: "#2DD9E8",
          blueDeep: "#2F5CE0",
          purpleDeep: "#7C3AED",
        },
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(115deg, #4F7CFF 0%, #9D5CFF 55%, #2DD9E8 100%)",
        "brand-gradient-soft": "linear-gradient(135deg, rgba(79,124,255,0.18) 0%, rgba(157,92,255,0.16) 50%, rgba(45,217,232,0.14) 100%)",
        "brand-radial-1": "radial-gradient(closest-side, rgba(79,124,255,0.55), transparent)",
        "brand-radial-2": "radial-gradient(closest-side, rgba(157,92,255,0.5), transparent)",
        "brand-radial-3": "radial-gradient(closest-side, rgba(45,217,232,0.4), transparent)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(157,92,255,0.15), 0 8px 30px -6px rgba(79,124,255,0.35), 0 2px 12px -2px rgba(45,217,232,0.2)",
        "glow-lg": "0 0 0 1px rgba(157,92,255,0.18), 0 20px 60px -12px rgba(79,124,255,0.45), 0 8px 30px -8px rgba(157,92,255,0.3)",
        glass: "0 8px 40px -8px rgba(0,0,0,0.55), inset 0 1px 0 0 rgba(255,255,255,0.06)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["\"Space Grotesk\"", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
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
