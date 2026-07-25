"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

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
    { href: "/", label: "대시보드" },
    { href: "/live", label: "실시간" },
    { href: "/categories", label: "종류별 종목" },
    { href: "/holdings", label: "보유종목" },
    { href: "/ranking", label: "자산 랭킹" },
    { href: "/watchlist", label: "관심" },
    { href: "/orders", label: "주문/거래" },
  ];

  return (
    <nav className="sticky top-0 z-10 border-b border-bg-3 bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="text-lg font-bold text-ink-1">
          papertrade
        </Link>
        <div className="flex items-center gap-1">
          {tabs.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
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
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
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
              className="ml-2 rounded-lg border border-bg-3 px-3 py-1.5 text-sm text-ink-2 hover:bg-bg-2"
            >
              로그아웃
            </button>
          ) : (
            <Link
              href="/login"
              className="ml-2 rounded-lg bg-brand px-3 py-1.5 text-sm font-semibold text-brand-fg"
            >
              로그인
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
