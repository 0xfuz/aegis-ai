import type { Config } from "tailwindcss";

// Tokens transcribed 1:1 from AEGIS_AI_UIUX_SPEC.md § 1.2-1.3 — if a value
// changes, update the spec doc in the same commit so they never drift.
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#0A0D12",
        surface: "#12161D",
        "surface-raised": "#1A2029",
        hairline: "#252C38",
        "text-primary": "#E8ECF2",
        "text-muted": "#8A93A3",
        signal: "#4DD8E8",
        cognition: "#9B8CFF",
        severity: {
          critical: "#E5484D",
          high: "#F2994A",
          medium: "#F2C94C",
          low: "#4DD8E8",
          info: "#6B7280",
        },
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-plex-mono)", "monospace"],
      },
      borderRadius: {
        DEFAULT: "8px",
        card: "12px",
      },
    },
  },
  plugins: [],
};

export default config;
