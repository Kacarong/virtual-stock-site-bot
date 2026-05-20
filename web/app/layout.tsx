import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "papertrade",
  description: "개인용 가상 주식·코인 모의투자",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
