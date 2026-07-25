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
        // 라이트/다크 테마 토큰 (globals.css의 CSS 변수 참조)
        ink: {
          1: "rgb(var(--ink-1) / <alpha-value>)",
          2: "rgb(var(--ink-2) / <alpha-value>)",
          3: "rgb(var(--ink-3) / <alpha-value>)",
          4: "rgb(var(--ink-4) / <alpha-value>)",
        },
        bg: {
          1: "rgb(var(--bg-1) / <alpha-value>)",
          2: "rgb(var(--bg-2) / <alpha-value>)",
          3: "rgb(var(--bg-3) / <alpha-value>)",
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
