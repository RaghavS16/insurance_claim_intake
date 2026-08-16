import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "va-canvas": "var(--va-canvas)",
        "va-canvas-elevated": "var(--va-canvas-elevated)",
        "va-surface": "var(--va-surface)",
        "va-surface-hover": "var(--va-surface-hover)",
        "va-border": "var(--va-border)",
        "va-border-strong": "var(--va-border-strong)",
        "va-text-primary": "var(--va-text-primary)",
        "va-text-secondary": "var(--va-text-secondary)",
        "va-text-tertiary": "var(--va-text-tertiary)",
        "va-accent": "var(--va-accent)",
        "va-accent-soft": "var(--va-accent-soft)",
        "va-state-idle": "var(--va-state-idle)",
        "va-state-connecting": "var(--va-state-connecting)",
        "va-state-listening": "var(--va-state-listening)",
        "va-state-thinking": "var(--va-state-thinking)",
        "va-state-speaking": "var(--va-state-speaking)",
        "va-state-error": "var(--va-state-error)",
      },
      borderRadius: {
        "va-sm": "var(--va-radius-sm)",
        "va-md": "var(--va-radius-md)",
        "va-lg": "var(--va-radius-lg)",
        "va-full": "var(--va-radius-full)",
      },
      boxShadow: {
        "va-sm": "var(--va-shadow-sm)",
        "va-md": "var(--va-shadow-md)",
        "va-glow": "var(--va-shadow-glow)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
