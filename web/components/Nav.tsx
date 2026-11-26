"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

type Me = {
  id: number;
  username: string;
  is_admin: boolean;
};

export function Nav() {
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => setMe(null));
  }, [path]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  const tabs = [
    { href: "/", label: "홈" },
    { href: "/categories", label: "종류별 종목" },
    { href: "/account", label: "내 계좌" },
    { href: "/ranking", label: "자산 랭킹" },
    { href: "/watchlist", label: "관심" },
  ];

  return (
    <nav className="sticky top-0 z-10 border-b border-bg-3 bg-bg-1/80 backdrop-blur">
      {/* 좁은 화면에선 메뉴가 둘째 줄로 내려가고 가로 스크롤 (글자가 세로로 쪼개지던 문제) */}
      <div className="flex w-full flex-wrap items-center justify-between gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="shrink-0 text-lg font-bold text-ink-1">
          papertrade
        </Link>
        <div className="flex max-w-full items-center gap-1 overflow-x-auto whitespace-nowrap">
          <ThemeToggle />
          {tabs.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition ${
                path === t.href
                  ? "bg-brand text-brand-fg"
                  : "text-ink-2 hover:bg-bg-2"
              }`}
            >
              {t.label}
            </Link>
          ))}
          {me?.is_admin && (
            <Link
              href="/admin"
              className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition ${
                path === "/admin"
                  ? "bg-brand text-brand-fg"
                  : "text-ink-2 hover:bg-bg-2"
              }`}
            >
              관리자
            </Link>
          )}
          {me ? (
            <button
              onClick={logout}
              className="ml-2 shrink-0 rounded-lg border border-bg-3 px-3 py-1.5 text-sm text-ink-2 hover:bg-bg-2"
            >
              로그아웃
            </button>
          ) : (
            <Link
              href="/login"
              className="ml-2 shrink-0 rounded-lg bg-brand px-3 py-1.5 text-sm font-semibold text-brand-fg"
            >
              로그인
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
