"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtPrice, pctClass } from "@/lib/api";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  value: number | null;
};

type Sort = "value" | "volume" | "change";

const SORTS: { key: Sort; label: string }[] = [
  { key: "value", label: "거래대금" },
  { key: "volume", label: "거래량" },
  { key: "change", label: "급등" },
];

const fetcher = (u: string) => api(u);

function fmtCompact(n: number): string {
  if (!isFinite(n)) return "-";
  const abs = Math.abs(n);
  if (abs >= 1e12) return (n / 1e12).toFixed(1) + "조";
  if (abs >= 1e8) return (n / 1e8).toFixed(1) + "억";
  if (abs >= 1e4) return (n / 1e4).toFixed(1) + "만";
  return Math.round(n).toLocaleString();
}

function PopularPanel({
  market,
  title,
  refreshMs,
}: {
  market: "KRX" | "US" | "UPBIT";
  title: string;
  refreshMs: number;
}) {
  const [sort, setSort] = useState<Sort>("value");
  // 해외주식만 USD/KRW 토글
  const [showKrw, setShowKrw] = useState(false);

  const { data, isLoading, error } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=10`,
    fetcher,
    { refreshInterval: refreshMs, keepPreviousData: true }
  );

  // 환율 (US 패널만)
  const { data: fx } = useSWR<{ usdkrw: string }>(
    market === "US" ? "/portfolio" : null,
    fetcher,
    { refreshInterval: 60000 }
  );
  const rate = fx?.usdkrw ? Number(fx.usdkrw) : null;

  return (
    <div className="flex flex-col rounded-3xl bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-bg-3 px-5 py-3">
        <h3 className="font-semibold">{title}</h3>
        <div className="flex gap-1">
          {SORTS.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`rounded-full px-2.5 py-1 text-xs ${
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
        <div className="flex justify-end gap-1 border-b border-bg-3 px-5 py-2">
          <button
            onClick={() => setShowKrw(false)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] ${
              !showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            달러로 보기
          </button>
          <button
            onClick={() => setShowKrw(true)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] ${
              showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            원화로 보기
          </button>
        </div>
      )}

      <div className="flex-1">
        {error ? (
          <div className="p-6 text-center text-xs text-red-500">불러오기 실패</div>
        ) : isLoading && !data ? (
          <div className="p-6 text-center text-xs text-ink-3">불러오는 중…</div>
        ) : !data?.length ? (
          <div className="p-6 text-center text-xs text-ink-3">데이터 없음</div>
        ) : (
          <ul className="divide-y divide-bg-3">
            {data.map((r, i) => {
              const priceNum = r.price ?? 0;
              const changePct = r.change_pct ?? 0;
              const volNum = r.volume ?? 0;
              const valNum = r.value ?? 0;
              // US + 원화 표시 모드 — 환율 곱해서 KRX처럼 표시
              const displayPrice =
                market === "US" && showKrw && rate ? priceNum * rate : priceNum;
              const displayMarket =
                market === "US" && showKrw ? "KRX" : r.market;
              return (
                <li key={`${r.market}-${r.code}`}>
                  <Link
                    href={`/symbols/${r.market}/${encodeURIComponent(r.code)}`}
                    className="flex items-center gap-3 px-5 py-2.5 hover:bg-bg-2"
                  >
                    <span className="w-5 text-right text-xs text-ink-3">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {r.name}
                      </div>
                      <div className="text-[11px] text-ink-3">
                        {sort === "volume"
                          ? fmtCompact(volNum)
                          : fmtCompact(valNum)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold">
                        {r.price == null
                          ? "-"
                          : fmtPrice(displayPrice, displayMarket)}
                      </div>
                      <div className={`text-[11px] ${pctClass(changePct)}`}>
                        {r.change_pct == null
                          ? "-"
                          : `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-bg-3 px-5 py-2 text-center">
        <Link
          href={`/popular/${market}`}
          className="text-[11px] text-ink-3 hover:text-ink-1"
        >
          전체보기 →
        </Link>
      </div>
    </div>
  );
}

export function PopularBoard() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <PopularPanel market="KRX" title="국내주식" refreshMs={30000} />
      <PopularPanel market="US" title="해외주식" refreshMs={30000} />
      <PopularPanel market="UPBIT" title="코인" refreshMs={5000} />
    </div>
  );
}
