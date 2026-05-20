"use client";

import { api } from "@/lib/api";
import { useState } from "react";

export default function Login() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function devLogin() {
    setLoading(true);
    setError(null);
    try {
      await api("/auth/dev-login", { method: "POST" });
      window.location.href = "/";
    } catch (e: any) {
      setError(e.message);
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
          Discord 계정으로 로그인하세요.
        </p>

        <button
          onClick={discordLogin}
          className="mt-6 w-full rounded-2xl bg-[#5865F2] py-3 text-sm font-semibold text-white hover:opacity-90"
        >
          Discord로 로그인
        </button>

        <div className="my-6 flex items-center gap-3 text-xs text-ink-3">
          <div className="h-px flex-1 bg-bg-3" />
          <span>또는</span>
          <div className="h-px flex-1 bg-bg-3" />
        </div>

        <button
          onClick={devLogin}
          disabled={loading}
          className="w-full rounded-2xl border border-bg-3 py-3 text-sm font-semibold text-ink-2 hover:bg-bg-2 disabled:opacity-50"
        >
          {loading ? "처리 중…" : "DEV 로그인 (개발용)"}
        </button>

        {error && (
          <p className="mt-3 rounded bg-red-50 p-3 text-xs text-red-700">{error}</p>
        )}
      </div>
    </div>
  );
}
