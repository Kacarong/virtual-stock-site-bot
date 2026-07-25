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
    <html lang="ko" suppressHydrationWarning>
      <head>
        {/* 초기 테마 적용 (하이드레이션 전 깜빡임 방지) */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&window.matchMedia('(prefers-color-scheme: dark)').matches)){document.documentElement.classList.add('dark')}}catch(e){}`,
          }}
        />
      </head>
      <body className="min-h-screen bg-bg-2 font-sans text-ink-1">
        <SwrProvider>
          <Nav />
          <div className="mx-auto max-w-5xl px-4 py-6">{children}</div>
        </SwrProvider>
      </body>
    </html>
  );
}
