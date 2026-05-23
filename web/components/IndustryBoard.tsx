"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtPrice, pctClass } from "@/lib/api";

type Item = {
  symbol_id: number | null;
  market: string;
  code: string;
  name: string;
  currency: string;
  price: number | null;
  change_pct: number | null;
};

type Group = {
  key: string;
  label: string;
  items: Item[];
};

const fetcher = (u: string) => api(u);

export function IndustryBoard() {
  const { data, isLoading } = useSWR<Group[]>("/market/industries", fetcher, {
    refreshInterval: 30000,
    keepPreviousData: true,
  });
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const groups = data || [];
  const active =
    groups.find((g) => g.key === activeKey) || groups[0] || null;

  return (
    <div className="rounded-3xl bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-bg-3 px-6 py-4">
        <h2 className="font-semibold">종류별 종목</h2>
        <span className="text-[11px] text-ink-3">업종·테마별 큐레이션</span>
      </div>

      {isLoading && !data ? (
        <div className="p-8 text-center text-sm text-ink-3">불러오는 중…</div>
      ) : groups.length === 0 ? (
        <div className="p-8 text-center text-sm text-ink-3">데이터 없음</div>
      ) : (
        <>
          {/* 카테고리 탭 — 가로 스크롤 */}
          <div className="flex gap-1 overflow-x-auto border-b border-bg-3 px-4 py-3">
            {groups.map((g) => (
              <button
                key={g.key}
                onClick={() => setActiveKey(g.key)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs whitespace-nowrap ${
                  (active?.key || groups[0].key) === g.key
                    ? "bg-ink-1 text-white"
                    : "bg-bg-2 text-ink-3 hover:bg-bg-3"
                }`}
              >
                {g.label}
              </button>
            ))}
          </div>

          {/* 종목 그리드 */}
          {active && active.items.length > 0 ? (
            <ul className="grid grid-cols-2 gap-px bg-bg-3 sm:grid-cols-3">
              {active.items.map((it) => (
                <li key={`${it.market}-${it.code}`} className="bg-white">
                  <Link
                    href={`/symbols/${it.market}/${encodeURIComponent(it.code)}`}
                    className="block px-4 py-3 hover:bg-bg-2"
                  >
                    <div className="truncate text-sm font-semibold">
                      {it.name}
                    </div>
                    <div className="mt-0.5 text-[10px] text-ink-3">
                      {it.market} · {it.code}
                    </div>
                    <div className="mt-1 flex items-baseline justify-between gap-2">
                      <span className="text-sm font-semibold">
                        {it.price !== null && isFinite(it.price)
                          ? fmtPrice(it.price, it.market, it.currency)
                          : "-"}
                      </span>
                      <span
                        className={`text-[11px] ${
                          it.change_pct !== null && isFinite(it.change_pct)
                            ? pctClass(it.change_pct)
                            : "text-ink-3"
                        }`}
                      >
                        {it.change_pct !== null && isFinite(it.change_pct)
                          ? `${it.change_pct >= 0 ? "+" : ""}${it.change_pct.toFixed(2)}%`
                          : "-"}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="p-8 text-center text-sm text-ink-3">
              종목 없음
            </div>
          )}
        </>
      )}
    </div>
  );
}
