"use client";

import { useEffect, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";

const fetcher = (u: string) => api(u);

function speak(text: string) {
  try {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
  } catch {}
}

/**
 * 체결 음성 안내 — 체결 내역(/orders/trades)을 주기적으로 확인해
 * 새 체결이 생기면 "매수/매도 체결되었습니다"를 읽어준다.
 * (즉시 체결 + 예약/지정가 지연 체결 모두 커버)
 */
export function TradeAnnouncer() {
  const { data } = useSWR<any[]>("/orders/trades", fetcher, {
    refreshInterval: 4000,
    shouldRetryOnError: false,
  });
  const lastId = useRef<number | null>(null);

  useEffect(() => {
    if (!data || data.length === 0) return;
    const maxId = Math.max(...data.map((t) => Number(t.id) || 0));
    if (lastId.current === null) {
      lastId.current = maxId; // 첫 로드는 기준점만 잡고 안내하지 않음
      return;
    }
    const base = lastId.current;
    const fresh = data
      .filter((t) => Number(t.id) > base)
      .sort((a, b) => Number(a.id) - Number(b.id));
    for (const t of fresh) {
      speak(t.side === "BUY" ? "매수 체결되었습니다" : "매도 체결되었습니다");
    }
    if (maxId > base) lastId.current = maxId;
  }, [data]);

  return null;
}
