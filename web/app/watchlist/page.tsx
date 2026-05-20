"use client";

import Link from "next/link";
import useSWR from "swr";
import { api, fmtNum, pctClass } from "@/lib/api";

const fetcher = (u: string) => api(u);

export default function Watchlist() {
  const { data, mutate } = useSWR<any[]>("/watchlist", fetcher, {
    refreshInterval: 2000,
  });

  async function remove(id: number) {
    await api(`/watchlist/${id}`, { method: "DELETE" });
    mutate();
  }

  return (
    <div className="rounded-3xl bg-white shadow-sm">
      <div className="border-b border-bg-3 px-6 py-4">
        <h2 className="font-semibold">관심 종목</h2>
      </div>
      {!data?.length ? (
        <div className="p-8 text-center text-sm text-ink-3">
          관심 종목 없음. 종목 페이지에서 ★ 추가하세요.
        </div>
      ) : (
        <ul className="divide-y divide-bg-3">
          {data.map((w) => {
            const change =
              w.price && w.prev_close
                ? ((Number(w.price) - Number(w.prev_close)) / Number(w.prev_close)) * 100
                : null;
            return (
              <li
                key={w.symbol_id}
                className="flex items-center justify-between px-6 py-4 hover:bg-bg-2"
              >
                <Link href={`/symbols/${w.market}/${w.code}`} className="flex-1">
                  <div className="font-semibold">{w.name}</div>
                  <div className="text-xs text-ink-3">
                    {w.market} · {w.code}
                  </div>
                </Link>
                <div className="text-right">
                  <div className="font-semibold">
                    {w.price ? fmtNum(w.price, 2) : "-"}
                  </div>
                  {change !== null && (
                    <div className={`text-xs ${pctClass(change.toString())}`}>
                      {change >= 0 ? "+" : ""}
                      {change.toFixed(2)}%
                    </div>
                  )}
                </div>
                <button
                  onClick={() => remove(w.symbol_id)}
                  className="ml-4 rounded border border-bg-3 px-2 py-1 text-xs text-ink-3 hover:bg-bg-3"
                >
                  삭제
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
