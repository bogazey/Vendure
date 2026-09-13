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
        slate: {
          50: "var(--color-slate-50)",
          100: "var(--color-slate-100)",
          200: "var(--color-slate-200)",
          300: "var(--color-slate-300)",
          400: "var(--color-slate-400)",
          500: "var(--color-slate-500)",
          600: "var(--color-slate-600)",
        },
        brand: {
          blue: "#3B82F6",
          purple: "#8B5CF6",
          aqua: "#22D3EE",
        },
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, #22D3EE 0%, #3B82F6 55%, #8B5CF6 100%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(139,92,246,0.15), 0 8px 30px -6px rgba(59,130,246,0.35), 0 2px 12px -2px rgba(34,211,238,0.2)",
      },
      fontFamily: {
        sans: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["Sora", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
