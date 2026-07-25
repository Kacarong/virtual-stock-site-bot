"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Hit = {
  id: number;
  code: string;
  name: string;
  market: string;
  asset_type: string;
};

export function SearchBox() {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const timer = useRef<any>(null);

  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const list = await api<Hit[]>(`/market/search?q=${encodeURIComponent(q)}`);
        setHits(list);
      } catch {
        setHits([]);
      }
    }, 200);
  }, [q]);

  function go(h: Hit) {
    router.push(`/symbols/${h.market}/${h.code}`);
    setOpen(false);
    setQ("");
  }

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="종목명 또는 코드 검색 (예: 삼성, 005930, AAPL, KRW-BTC)"
        className="w-full rounded-2xl border border-bg-3 bg-bg-2 px-4 py-3 text-sm outline-none focus:border-brand focus:bg-bg-1"
      />
      {open && hits.length > 0 && (
        <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-2xl border border-bg-3 bg-bg-1 shadow-lg">
          {hits.map((h) => (
            <button
              key={h.id}
              onMouseDown={() => go(h)}
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-bg-2"
            >
              <div>
                <div className="text-sm font-semibold text-ink-1">{h.name}</div>
                <div className="text-xs text-ink-3">
                  {h.market} · {h.code}
                </div>
              </div>
              <span className="rounded bg-bg-3 px-2 py-0.5 text-xs text-ink-2">
                {h.asset_type}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
