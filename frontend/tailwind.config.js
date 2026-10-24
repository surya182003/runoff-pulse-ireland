/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 950: "#06152b", 900: "#0b2545", 800: "#13315c", 700: "#1d3f6e", 600: "#38557f" },
        ocean: { 50: "#eef6fd", 100: "#d6e9fa", 500: "#2a78d6", 600: "#256abf", 700: "#1c5cab" },
        reef: { 50: "#ecfbf7", 100: "#cff5ea", 500: "#14a085", 600: "#0f8a73", 700: "#0b6f5d" },
        status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", '"Segoe UI"', "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(11, 37, 69, 0.06), 0 1px 1px rgba(11, 37, 69, 0.04)",
      },
    },
  },
  plugins: [],
};
