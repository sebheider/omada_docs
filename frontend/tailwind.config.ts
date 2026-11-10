import type { Config } from 'tailwindcss';
import typography from '@tailwindcss/typography';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['system-ui', '-apple-system', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        brand: {
          50: '#eef8f6', 100: '#d5eee9', 200: '#ade0d5', 300: '#7ccabb', 400: '#4aae9d',
          500: '#2f9383', 600: '#23766a', 700: '#1f5f57', 800: '#1c4d47', 900: '#1a413c', 950: '#0a2522',
        },
      },
    },
  },
  plugins: [typography],
} satisfies Config;
