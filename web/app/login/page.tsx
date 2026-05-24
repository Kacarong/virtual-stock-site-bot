"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function Login() {
  const [showAdmin, setShowAdmin] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function adminLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api("/auth/admin-login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      window.location.href = "/";
    } catch (e: any) {
      setError(e.message || "로그인 실패");
      setLoading(false);
    }
  }

  function discordLogin() {
    window.location.href = "/api/auth/discord/login";
  }

  return (
    <div className="mx-auto mt-16 max-w-md">
      <div className="rounded-3xl bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-bold">로그인</h1>
        <p className="mt-2 text-sm text-ink-3">
          Discord 계정으로 로그인하여 모의투자를 시작하세요.
        </p>

        <button
          onClick={discordLogin}
          className="mt-6 w-full rounded-2xl bg-[#5865F2] py-3 text-sm font-semibold text-white hover:opacity-90"
        >
          Discord로 로그인
        </button>

        <div className="my-6 flex items-center gap-3 text-xs text-ink-3">
          <div className="h-px flex-1 bg-bg-3" />
          <span>관리자</span>
          <div className="h-px flex-1 bg-bg-3" />
        </div>

        {!showAdmin ? (
          <button
            onClick={() => setShowAdmin(true)}
            className="w-full rounded-2xl border border-bg-3 py-3 text-sm font-semibold text-ink-3 hover:bg-bg-2"
          >
            관리자 로그인
          </button>
        ) : (
          <form onSubmit={adminLogin} className="space-y-3">
            <input
              type="text"
              autoComplete="username"
              placeholder="아이디"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-xl border border-bg-3 px-4 py-3 text-sm outline-none focus:border-brand"
              required
            />
            <input
              type="password"
              autoComplete="current-password"
              placeholder="비밀번호"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-bg-3 px-4 py-3 text-sm outline-none focus:border-brand"
              required
            />
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-2xl bg-ink-1 py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "로그인 중…" : "관리자 로그인"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowAdmin(false);
                setError(null);
                setUsername("");
                setPassword("");
              }}
              className="w-full text-xs text-ink-3 hover:text-ink-1"
            >
              취소
            </button>
          </form>
        )}

        {error && (
          <p className="mt-3 rounded bg-red-50 p-3 text-xs text-red-700">{error}</p>
        )}
      </div>
    </div>
  );
}
