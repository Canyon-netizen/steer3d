/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        baseline: "#4a9eff",
        steered: "#ff7a45",
        accent: "#9c27b0",
        bg: "#0a0d12",
        panel: "#11151c",
        border: "#1f2630",
      },
    },
  },
  plugins: [],
};