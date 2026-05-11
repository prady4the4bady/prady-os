/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "SF Pro Display",
          "SF Pro Text",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif"
        ],
      },
      colors: {
        menubar: {
          light: "#EBEBEB",
          dark: "#1E1E1E",
        },
        desktop: {
          light: "#F5F5F5",
          dark: "#2D2D2D",
        },
      },
      keyframes: {
        drift: {
          "0%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
          "100%": { backgroundPosition: "0% 50%" },
        },
        bounceSoft: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
      animation: {
        drift: "drift 24s ease-in-out infinite",
        bounceSoft: "bounceSoft 0.35s ease",
      },
      boxShadow: {
        glass: "0 10px 30px rgba(0, 0, 0, 0.20)",
      },
    },
  },
  plugins: [],
};
