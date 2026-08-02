"use client";

import useSWR from "swr";
import { api, fmtKRW } from "@/lib/api";

type Notice = {
  id: number;
  title: string;
  message: string | null;
  amount_krw: string;
  created_at: string;
};

const fetcher = (u: string) => api(u);

/** 사이트 입장 시 미확인 지원금 알림을 우측 하단 토스트로 표시. 끄기(닫기) 가능. */
export function SupportNotifications() {
  const { data, mutate } = useSWR<Notice[]>("/support/notifications", fetcher, {
    refreshInterval: 30000,
    shouldRetryOnError: false, // 비로그인(401) 시 조용히 무시
  });

  if (!data || data.length === 0) return null;

  async function dismiss(id: number) {
    // 낙관적 제거
    mutate(
      (cur) => (cur || []).filter((n) => n.id !== id),
      { revalidate: false }
    );
    try {
      await api(`/support/notifications/${id}/dismiss`, { method: "POST" });
    } catch {}
    mutate();
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-[min(92vw,360px)] flex-col gap-2">
      {data.map((n) => (
        <div
          key={n.id}
          className="rounded-2xl border border-brand/30 bg-bg-1 p-4 shadow-lg"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">🎁</span>
              <div className="font-bold text-brand">지원금 도착</div>
            </div>
            <button
              onClick={() => dismiss(n.id)}
              className="rounded-lg px-2 py-0.5 text-sm text-ink-3 hover:bg-bg-2"
              title="알림 끄기"
            >
              ✕
            </button>
          </div>
          <div className="mt-2 text-sm font-semibold">{n.title}</div>
          {n.message && (
            <div className="mt-1 whitespace-pre-wrap text-xs text-ink-2">
              {n.message}
            </div>
          )}
          <div className="mt-2 text-lg font-bold text-up">
            +{fmtKRW(n.amount_krw)}
          </div>
          <button
            onClick={() => dismiss(n.id)}
            className="mt-3 w-full rounded-xl bg-bg-2 py-2 text-xs font-semibold text-ink-2 hover:bg-bg-3"
          >
            확인 (알림 끄기)
          </button>
        </div>
      ))}
    </div>
  );
}
