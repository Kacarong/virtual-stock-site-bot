import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // 토스 스타일 팔레트
        brand: {
          DEFAULT: "#3182F6",
          fg: "#FFFFFF",
        },
        up: "#FF4D4D",   // 한국식: 상승 빨강
        down: "#3182F6", // 한국식: 하락 파랑
        ink: {
          1: "#191F28",
          2: "#4E5968",
          3: "#8B95A1",
          4: "#B0B8C1",
        },
        bg: {
          1: "#FFFFFF",
          2: "#F9FAFB",
          3: "#F2F4F6",
        },
      },
      fontFamily: {
        sans: ["Pretendard", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
