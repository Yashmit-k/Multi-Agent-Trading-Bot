/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0B0F14",
          sidebar: "#0F141B",
          card: "#121922",
          elevated: "#171F2A",
          border: "#26303C",
        },
      },
    },
  },
  plugins: [],
};
