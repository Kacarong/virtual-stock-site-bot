import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  // 동적 className 또는 JIT가 놓치는 색상 보장
  safelist: [
    "bg-green-100", "text-green-700",
    "bg-red-100", "text-red-700",
    "bg-yellow-50", "text-yellow-700",
    "bg-green-50", "text-green-700",
  ],
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
