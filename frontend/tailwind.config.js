/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        soft: 'var(--soft)',
        card: 'var(--card)',
        line: 'var(--border)',
        strong: 'var(--border-strong)',
        fg: 'var(--fg)',
        muted: 'var(--muted)',
        accent: 'var(--accent)',
        'accent-hover': 'var(--accent-hover)',
        'accent-fg': 'var(--accent-fg)',
        inverse: 'var(--inverse-bg)',
        'inverse-fg': 'var(--inverse-fg)',
        success: 'var(--success)',
        danger: 'var(--danger)',
        warning: 'var(--warning)',
        info: 'var(--info)',
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Oswald', 'Arial Narrow', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'Consolas', 'monospace'],
      },
      boxShadow: { card: '0 1px 0 rgba(17,17,17,0.04), 0 2px 6px rgba(17,17,17,0.04)' },
    },
  },
  plugins: [],
};
