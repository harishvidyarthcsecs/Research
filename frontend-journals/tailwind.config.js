/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: {
          50: '#eef2ff',
          100: '#e0e7ff',
          200: '#c7d2fe',
          300: '#a5b4fc',
          400: '#818cf8',
          500: '#6366f1',
          600: '#5457e5',
          700: '#4338ca',
          800: '#3730a3',
          900: '#312e81',
        },
        violet: {
          500: '#8b5cf6',
        },
        neutral: {
          50: '#fafafa',
          100: '#f5f5f5',
          200: '#e5e5e5',
          300: '#d4d4d4',
          400: '#a3a3a3',
          500: '#737373',
          600: '#525252',
          700: '#404040',
          800: '#262626',
          900: '#171717',
          950: '#0a0a0a',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        'mesh-light':
          'radial-gradient(at 0% 0%, rgba(99,102,241,0.14) 0px, transparent 50%), ' +
          'radial-gradient(at 100% 0%, rgba(139,92,246,0.12) 0px, transparent 50%), ' +
          'radial-gradient(at 100% 100%, rgba(99,102,241,0.10) 0px, transparent 50%), ' +
          'radial-gradient(at 0% 100%, rgba(139,92,246,0.10) 0px, transparent 50%)',
        'mesh-dark':
          'radial-gradient(at 0% 0%, rgba(99,102,241,0.20) 0px, transparent 50%), ' +
          'radial-gradient(at 100% 0%, rgba(139,92,246,0.18) 0px, transparent 50%), ' +
          'radial-gradient(at 100% 100%, rgba(99,102,241,0.14) 0px, transparent 50%), ' +
          'radial-gradient(at 0% 100%, rgba(139,92,246,0.14) 0px, transparent 50%)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-500px 0' },
          '100%': { backgroundPosition: '500px 0' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s linear infinite',
        'fade-in': 'fade-in 0.35s ease-out both',
        'slide-up': 'slide-up 0.4s ease-out both',
      },
    },
  },
  plugins: [],
}
