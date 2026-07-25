"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtPrice, pctClass } from "@/lib/api";
import { useUsdToKrw } from "@/lib/useUsdToKrw";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  value: number | null;
  market_cap?: number | null;
};

type Sort = "value" | "volume" | "change" | "decline" | "market_cap";

const SORTS: { key: Sort; label: string }[] = [
  { key: "value", label: "거래대금" },
  { key: "volume", label: "거래량" },
  { key: "market_cap", label: "시가총액" },
  { key: "change", label: "급등" },
  { key: "decline", label: "급락" },
];

const TITLES: Record<string, string> = {
  KRX: "국내주식 인기 100",
  US: "해외주식 인기 100",
  UPBIT: "코인 인기 100",
};

const fetcher = (u: string) => api(u);

function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  const v = Number(n);
  if (!isFinite(v)) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + "조";
  if (abs >= 1e8) return (v / 1e8).toFixed(1) + "억";
  if (abs >= 1e4) return (v / 1e4).toFixed(1) + "만";
  return Math.round(v).toLocaleString();
}

export default function PopularDetailPage({
  params,
}: {
  params: { market: string };
}) {
  const market = params.market.toUpperCase();
  const [sort, setSort] = useState<Sort>("value");
  // 대시보드/상세 페이지와 동일한 USD/KRW 토글 (localStorage 공유)
  const [showKrw, setShowKrw] = useUsdToKrw();
  const sortsForMarket = SORTS.filter(
    (s) => !(market === "UPBIT" && s.key === "market_cap")
  );

  const { data, isLoading } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=100`,
    fetcher,
    {
      refreshInterval: market === "UPBIT" ? 5000 : 30000,
      keepPreviousData: true,
    }
  );

  const { data: fx } = useSWR<{ usdkrw: string }>(
    market === "US" ? "/portfolio" : null,
    fetcher,
    { refreshInterval: 60000 }
  );
  const rate = fx?.usdkrw ? Number(fx.usdkrw) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/" className="text-xs text-ink-3 hover:text-ink-1">
            ← 대시보드
          </Link>
          <h1 className="mt-1 text-2xl font-bold">
            {TITLES[market] || "인기 종목"}
          </h1>
        </div>
        <div className="flex flex-wrap gap-1">
          {sortsForMarket.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`rounded-full px-3 py-1.5 text-xs ${
                sort === s.key
                  ? "bg-ink-1 text-white"
                  : "bg-bg-2 text-ink-3 hover:bg-bg-3"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {market === "US" && (
        <div className="flex justify-end gap-1">
          <button
            onClick={() => setShowKrw(false)}
            className={`rounded-full px-3 py-1 text-[11px] ${
              !showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            달러로 보기
          </button>
          <button
            onClick={() => setShowKrw(true)}
            className={`rounded-full px-3 py-1 text-[11px] ${
              showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            원화로 보기
          </button>
        </div>
      )}

      <div className="rounded-3xl bg-bg-1 shadow-sm">
        {isLoading && !data ? (
          <div className="p-8 text-center text-sm text-ink-3">불러오는 중…</div>
        ) : !data?.length ? (
          <div className="p-8 text-center text-sm text-ink-3">데이터 없음</div>
        ) : (
          <ul className="divide-y divide-bg-3">
            {data.map((r, i) => {
              const priceNum =
                r.price === null || r.price === undefined
                  ? null
                  : Number(r.price);
              const validPrice = priceNum !== null && isFinite(priceNum);
              const displayPrice =
                validPrice && market === "US" && showKrw && rate
                  ? (priceNum as number) * rate
                  : priceNum;
              const displayMarket =
                market === "US" && showKrw && rate ? "KRX" : r.market;
              const chgNum =
                r.change_pct === null || r.change_pct === undefined
                  ? null
                  : Number(r.change_pct);
              const validChg = chgNum !== null && isFinite(chgNum);
              return (
                <li key={`${r.market}-${r.code}`}>
                  <Link
                    href={`/symbols/${r.market}/${encodeURIComponent(r.code)}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-bg-2"
                  >
                    <span className="w-7 text-right text-xs text-ink-3">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {r.name}
                      </div>
                      <div className="text-[11px] text-ink-3">
                        {r.market} · {r.code} ·{" "}
                        {sort === "volume"
                          ? `거래량 ${fmtCompact(r.volume)}`
                          : sort === "market_cap"
                          ? `시총 ${fmtCompact(r.market_cap)}`
                          : `거래대금 ${fmtCompact(r.value)}`}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold">
                        {validPrice
                          ? fmtPrice(displayPrice as number, displayMarket)
                          : "-"}
                      </div>
                      <div
                        className={`text-[11px] ${
                          validChg ? pctClass(chgNum as number) : "text-ink-3"
                        }`}
                      >
                        {validChg
                          ? `${(chgNum as number) >= 0 ? "+" : ""}${(chgNum as number).toFixed(2)}%`
                          : "-"}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
