"use client";

import { useEffect, useState } from "react";

type Me = {
  id: number;
  discord_id: string;
  username: string;
  cash_krw: string;
  cash_usd: string;
  is_admin: boolean;
};

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const r = await fetch("/api/auth/me", { credentials: "include" });
      if (r.status === 401) {
        setMe(null);
      } else if (r.ok) {
        setMe(await r.json());
      } else {
        setError(`API ${r.status}`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function devLogin() {
    setLoading(true);
    await fetch("/api/auth/dev-login", {
      method: "POST",
      credentials: "include",
    });
    await refresh();
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    await refresh();
  }

  if (loading) {
    return <main className="p-8 text-ink-2">불러오는 중…</main>;
  }

  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-bold text-ink-1">papertrade</h1>
      <p className="mt-1 text-sm text-ink-3">Stage 1 — 기반 구조 동작 확인</p>

      {error && (
        <div className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      {!me ? (
        <div className="mt-8 rounded-2xl bg-bg-2 p-6">
          <p className="text-ink-2">아직 로그인 안 됨</p>
          <button
            onClick={devLogin}
            className="mt-4 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-fg hover:opacity-90"
          >
            DEV 로그인 (개발용)
          </button>
          <p className="mt-3 text-xs text-ink-3">
            Stage 5에서 Discord OAuth 버튼으로 교체됩니다.
          </p>
        </div>
      ) : (
        <div className="mt-8 rounded-2xl bg-bg-2 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-ink-3">사용자</p>
              <p className="text-lg font-semibold text-ink-1">
                {me.username} {me.is_admin && <span className="ml-2 rounded bg-brand/10 px-2 py-0.5 text-xs text-brand">관리자</span>}
              </p>
              <p className="text-xs text-ink-3 mt-1">Discord ID: {me.discord_id}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg border border-bg-3 px-3 py-1.5 text-sm text-ink-2 hover:bg-bg-3"
            >
              로그아웃
            </button>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-4">
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs text-ink-3">현금 (KRW)</p>
              <p className="mt-1 text-xl font-bold text-ink-1">
                ₩ {Number(me.cash_krw).toLocaleString()}
              </p>
            </div>
            <div className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs text-ink-3">현금 (USD)</p>
              <p className="mt-1 text-xl font-bold text-ink-1">
                $ {Number(me.cash_usd).toLocaleString()}
              </p>
            </div>
          </div>

          <p className="mt-6 text-xs text-ink-3">
            다음 단계(Stage 2)에서 시세 폴러, Stage 3에서 거래 엔진이 붙습니다.
          </p>
        </div>
      )}
    </main>
  );
}
