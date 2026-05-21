"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtPrice, pctClass } from "@/lib/api";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number;
  change_pct: number;
  volume: number;
  value: number;
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

  const { data, isLoading, error } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=10`,
    fetcher,
    { refreshInterval: refreshMs, keepPreviousData: true }
  );

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

      <div className="flex-1">
        {error ? (
          <div className="p-6 text-center text-xs text-red-500">불러오기 실패</div>
        ) : isLoading && !data ? (
          <div className="p-6 text-center text-xs text-ink-3">불러오는 중…</div>
        ) : !data?.length ? (
          <div className="p-6 text-center text-xs text-ink-3">데이터 없음</div>
        ) : (
          <ul className="divide-y divide-bg-3">
            {data.map((r, i) => (
              <li key={`${r.market}-${r.code}`}>
                <Link
                  href={`/symbols/${r.market}/${encodeURIComponent(r.code)}`}
                  className="flex items-center gap-3 px-5 py-2.5 hover:bg-bg-2"
                >
                  <span className="w-5 text-right text-xs text-ink-3">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold">{r.name}</div>
                    <div className="text-[11px] text-ink-3">
                      {sort === "volume"
                        ? fmtCompact(r.volume)
                        : fmtCompact(r.value)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold">
                      {fmtPrice(r.price, r.market)}
                    </div>
                    <div className={`text-[11px] ${pctClass(r.change_pct)}`}>
                      {r.change_pct >= 0 ? "+" : ""}
                      {r.change_pct.toFixed(2)}%
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
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
