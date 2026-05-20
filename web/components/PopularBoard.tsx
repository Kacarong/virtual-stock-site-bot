"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtNum, pctClass } from "@/lib/api";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number;
  change_pct: number;
  volume: number;
  value: number;
};

type Market = "KRX" | "US" | "UPBIT";
type Sort = "value" | "volume" | "change";

const MARKETS: { key: Market; label: string }[] = [
  { key: "KRX", label: "국내주식" },
  { key: "US", label: "해외주식" },
  { key: "UPBIT", label: "코인" },
];

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

function detailHref(r: Row): string {
  return `/symbols/${r.market}/${encodeURIComponent(r.code)}`;
}

export function PopularBoard() {
  const [market, setMarket] = useState<Market>("KRX");
  const [sort, setSort] = useState<Sort>("value");

  const { data, isLoading } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=20`,
    fetcher,
    { refreshInterval: market === "UPBIT" ? 5000 : 30000 }
  );

  return (
    <div className="rounded-3xl bg-white shadow-sm">
      <div className="flex flex-wrap items-center gap-2 border-b border-bg-3 px-6 py-4">
        <h2 className="mr-4 font-semibold">실시간 인기</h2>
        <div className="flex gap-1">
          {MARKETS.map((m) => (
            <button
              key={m.key}
              onClick={() => setMarket(m.key)}
              className={`rounded-full px-3 py-1 text-xs ${
                market === m.key ? "bg-brand text-brand-fg" : "bg-bg-2 text-ink-2"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-1">
          {SORTS.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`rounded-full px-3 py-1 text-xs ${
                sort === s.key
                  ? "border border-ink-3 bg-white text-ink-1"
                  : "border border-transparent bg-bg-2 text-ink-3"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="p-8 text-center text-sm text-ink-3">불러오는 중…</div>
      ) : !data?.length ? (
        <div className="p-8 text-center text-sm text-ink-3">
          데이터 없음 (장 시작 후 또는 종목 마스터 동기화 후 표시)
        </div>
      ) : (
        <ul className="divide-y divide-bg-3">
          {data.map((r, i) => (
            <li key={`${r.market}-${r.code}`}>
              <Link
                href={detailHref(r)}
                className="flex items-center gap-4 px-6 py-3 hover:bg-bg-2"
              >
                <span className="w-6 text-right text-sm text-ink-3">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="truncate font-semibold">{r.name}</div>
                  <div className="text-xs text-ink-3">
                    {r.market} · {r.code}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold">{fmtNum(r.price, 2)}</div>
                  <div className={`text-xs ${pctClass(r.change_pct)}`}>
                    {r.change_pct >= 0 ? "+" : ""}
                    {r.change_pct.toFixed(2)}%
                  </div>
                </div>
                <div className="hidden w-24 text-right text-xs text-ink-3 sm:block">
                  {sort === "volume" ? fmtCompact(r.volume) : fmtCompact(r.value)}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
