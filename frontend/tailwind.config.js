/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0a",
        paper: "#fafaf7",
        bone: "#e8e4d8",
        muted: "#52524a",
        accent: "#d4ff3a",
        win: "#d4ff3a",
        draw: "#7a7a70",
        loss: "#ff5638",
      },
      fontFamily: {
        display: ['"Fraunces"', "ui-serif", "serif"],
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      letterSpacing: {
        tighter: "-0.04em",
        wider: "0.12em",
      },
    },
  },
  plugins: [],
};
