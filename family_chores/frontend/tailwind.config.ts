import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: [
          '"Nunito"',
          'system-ui',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'sans-serif',
        ],
        sans: [
          '"Nunito"',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
      },
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          900: '#312e81',
        },
      },
      spacing: {
        touch: '4.5rem',
      },
      borderRadius: {
        xl4: '2rem',
      },
      fontSize: {
        'fluid-xs': 'clamp(0.75rem, 0.6vw + 0.6rem, 1rem)',
        'fluid-sm': 'clamp(0.875rem, 0.8vw + 0.7rem, 1.125rem)',
        'fluid-base': 'clamp(1rem, 1vw + 0.8rem, 1.5rem)',
        'fluid-lg': 'clamp(1.25rem, 1.6vw + 0.9rem, 2.25rem)',
        'fluid-xl': 'clamp(1.75rem, 2.4vw + 1.1rem, 3.25rem)',
        'fluid-2xl': 'clamp(2.25rem, 3.2vw + 1.3rem, 4.5rem)',
        'fluid-3xl': 'clamp(3rem, 4vw + 1.5rem, 6rem)',
      },
      boxShadow: {
        tile: '0 12px 30px -12px rgba(79, 70, 229, 0.25)',
        card: '0 8px 20px -8px rgba(30, 27, 75, 0.15)',
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4,0,0.6,1) infinite',
        // F-U003 (UX sweep): bounce on the CelebrationAllDone emoji.
        // Defined here (not as an inline `style` attribute) so the
        // `prefers-reduced-motion` block in globals.css can disable it
        // alongside the rest of the decorative animations.
        'celebrate-bounce': 'celebrate-bounce 2.4s ease-in-out infinite',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'celebrate-bounce': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-12px)' },
        },
      },
    },
  },
  plugins: [],
} satisfies Config
