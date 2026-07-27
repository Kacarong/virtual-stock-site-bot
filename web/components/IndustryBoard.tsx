"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
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

type MarketKey = "ALL" | "KR" | "US" | "CRYPTO";

const MARKET_TABS: { key: MarketKey; label: string; match: (m: string) => boolean }[] = [
  { key: "ALL", label: "전체", match: () => true },
  { key: "KR", label: "국내", match: (m) => m === "KRX" },
  { key: "US", label: "미국", match: (m) => ["NASDAQ", "NYSE", "AMEX"].includes(m) },
  { key: "CRYPTO", label: "코인", match: (m) => m === "UPBIT" },
];

export function IndustryBoard() {
  const { data, isLoading } = useSWR<Group[]>("/market/industries", fetcher, {
    refreshInterval: (latest) => {
      // 가격이 절반 미만이면 빠른 재시도
      if (!latest) return 5000;
      const flat = latest.flatMap((g) => g.items);
      const priced = flat.filter((it) => it.price !== null).length;
      const ratio = flat.length ? priced / flat.length : 0;
      return ratio < 0.5 ? 5000 : 20000;
    },
    keepPreviousData: true,
  });
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [marketKey, setMarketKey] = useState<MarketKey>("ALL");

  const groups = data || [];
  const active =
    groups.find((g) => g.key === activeKey) || groups[0] || null;

  const filteredItems = useMemo(() => {
    if (!active) return [] as Item[];
    const mt = MARKET_TABS.find((t) => t.key === marketKey)!;
    return active.items.filter((it) => mt.match(it.market));
  }, [active, marketKey]);

  // 카테고리별 시장 보유 여부 (탭 disable 판단)
  const availableMarkets = useMemo(() => {
    if (!active) return new Set<MarketKey>();
    const s = new Set<MarketKey>(["ALL"]);
    for (const it of active.items) {
      if (it.market === "KRX") s.add("KR");
      else if (["NASDAQ", "NYSE", "AMEX"].includes(it.market)) s.add("US");
      else if (it.market === "UPBIT") s.add("CRYPTO");
    }
    return s;
  }, [active]);

  return (
    <div className="rounded-3xl bg-bg-1 shadow-sm">
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
          {/* 카테고리 탭 */}
          <div className="thin-scroll flex gap-1 overflow-x-auto border-b border-bg-3 px-4 py-3">
            {groups.map((g) => (
              <button
                key={g.key}
                onClick={() => {
                  setActiveKey(g.key);
                  setMarketKey("ALL");
                }}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs whitespace-nowrap ${
                  (active?.key || groups[0].key) === g.key
                    ? "bg-ink-1 text-bg-1"
                    : "bg-bg-2 text-ink-3 hover:bg-bg-3"
                }`}
              >
                {g.label}
                <span className="ml-1 text-[10px] opacity-60">
                  {g.items.length}
                </span>
              </button>
            ))}
          </div>

          {/* 시장 서브 필터 */}
          <div className="flex items-center gap-1 border-b border-bg-3 px-4 py-2">
            {MARKET_TABS.map((t) => {
              const enabled = availableMarkets.has(t.key);
              return (
                <button
                  key={t.key}
                  onClick={() => enabled && setMarketKey(t.key)}
                  disabled={!enabled}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                    marketKey === t.key
                      ? "bg-brand/10 text-brand"
                      : enabled
                        ? "text-ink-3 hover:bg-bg-2"
                        : "text-ink-3/40 cursor-not-allowed"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
            <span className="ml-auto text-[10px] text-ink-3">
              {filteredItems.length}종목
            </span>
          </div>

          {/* 종목 그리드 */}
          {filteredItems.length > 0 ? (
            <ul className="grid grid-cols-2 gap-px bg-bg-3 sm:grid-cols-3">
              {filteredItems.map((it) => (
                <li key={`${it.market}-${it.code}`} className="bg-bg-1">
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
              해당 시장에 종목이 없습니다
            </div>
          )}
        </>
      )}
    </div>
  );
}
