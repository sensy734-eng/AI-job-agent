import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17202a",
        paper: "#f8faf7",
        moss: "#3d6654",
        coral: "#d7674f",
        amber: "#d89a2b",
        aqua: "#3e8d96"
      },
      boxShadow: {
        panel: "0 12px 30px rgba(23, 32, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
