import "./globals.css";
import type { Metadata } from "next";
import { MyInvestmentPanel } from "@/components/MyInvestmentPanel";
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
          <div className="flex w-full gap-6 px-6 py-6">
            <main className="min-w-0 flex-1">{children}</main>
            {/* 오른쪽 상시 "내 투자" 패널 (Toss 스타일, lg 이상에서 표시) */}
            <aside className="hidden w-80 shrink-0 lg:block">
              <div className="sticky top-20">
                <MyInvestmentPanel />
              </div>
            </aside>
          </div>
        </SwrProvider>
      </body>
    </html>
  );
}
