import "./globals.css";
import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { SwrProvider } from "@/components/SwrProvider";

export const metadata: Metadata = {
  title: "papertrade",
  description: "개인용 가상 주식·코인 모의투자",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-bg-2 font-sans text-ink-1">
        <SwrProvider>
          <Nav />
          <div className="mx-auto max-w-5xl px-4 py-6">{children}</div>
        </SwrProvider>
      </body>
    </html>
  );
}
