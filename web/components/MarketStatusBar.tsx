"use client";

import useSWR from "swr";
import { api } from "@/lib/api";

type Status = {
  [m: string]: { open: boolean; next_open: string | null };
};

const fetcher = (u: string) => api(u);

const LABELS: { key: string; label: string }[] = [
  { key: "KRX", label: "국내" },
  { key: "NASDAQ", label: "나스닥" },
  { key: "NYSE", label: "NYSE" },
  { key: "UPBIT", label: "코인" },
];

export function MarketStatusBar() {
  const { data } = useSWR<Status>("/market/status", fetcher, {
    refreshInterval: 60000,
  });
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl bg-white px-4 py-2 shadow-sm">
      {LABELS.map((m) => {
        const open = data?.[m.key]?.open ?? (m.key === "UPBIT");
        return (
          <span
            key={m.key}
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              open ? "bg-up/10 text-up" : "bg-bg-2 text-ink-3"
            }`}
            title={
              !open && data?.[m.key]?.next_open
                ? "다음 개장: " +
                  new Date(data[m.key].next_open as string).toLocaleString("ko-KR")
                : ""
            }
          >
            <span>{open ? "●" : "○"}</span>
            {m.label} {open ? "거래가능" : "거래불가"}
          </span>
        );
      })}
    </div>
  );
}
