export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        bg: "hsl(var(--bg))",
        surface: "hsl(var(--surface))",
        subtle: "hsl(var(--subtle))",
        border: "hsl(var(--border))",
        text: "hsl(var(--text))",
        muted: "hsl(var(--muted))",
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        sev: {
          critical: "hsl(var(--sev-critical))",
          high: "hsl(var(--sev-high))",
          medium: "hsl(var(--sev-medium))",
          low: "hsl(var(--sev-low))",
          unknown: "hsl(var(--sev-unknown))",
        },
      },
      borderRadius: {
        DEFAULT: "6px",
        sm: "4px",
        md: "6px",
        lg: "6px",
      },
      maxWidth: {
        content: "1280px",
      },
      spacing: {
        grid: "4px",
      },
    },
  },
  plugins: [],
};
