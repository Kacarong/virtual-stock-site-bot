"use client";

import Link from "next/link";
import useSWR from "swr";
import { api, fmtNum, pctClass } from "@/lib/api";

const fetcher = (u: string) => api(u);

type WatchItem = {
  id?: number;
  symbol_id: number;
  code: string;
  name: string;
  market: string;
  price?: string | number | null;
  prev_close?: string | number | null;
};

const GROUPS: { key: string; label: string; markets: string[] }[] = [
  { key: "KRX", label: "국내주식", markets: ["KRX"] },
  { key: "US", label: "해외주식", markets: ["NASDAQ", "NYSE", "AMEX"] },
  { key: "UPBIT", label: "코인", markets: ["UPBIT"] },
];

function WatchRow({
  w,
  onRemove,
}: {
  w: WatchItem;
  onRemove: (id: number) => void;
}) {
  const change =
    w.price && w.prev_close
      ? ((Number(w.price) - Number(w.prev_close)) / Number(w.prev_close)) * 100
      : null;
  return (
    <li className="flex items-center justify-between px-6 py-4 hover:bg-bg-2">
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
        onClick={() => onRemove(w.symbol_id)}
        className="ml-4 rounded border border-bg-3 px-2 py-1 text-xs text-ink-3 hover:bg-bg-3"
      >
        삭제
      </button>
    </li>
  );
}

function WatchGroup({
  title,
  items,
  onRemove,
}: {
  title: string;
  items: WatchItem[];
  onRemove: (id: number) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="flex items-center justify-between px-6 py-2 text-xs text-ink-3">
        <span className="font-semibold">{title}</span>
        <span>{items.length}종목</span>
      </div>
      <ul className="divide-y divide-bg-3">
        {items.map((w) => (
          <WatchRow key={w.symbol_id} w={w} onRemove={onRemove} />
        ))}
      </ul>
    </div>
  );
}

export default function Watchlist() {
  const { data, mutate } = useSWR<WatchItem[]>("/watchlist", fetcher, {
    refreshInterval: 2000,
    keepPreviousData: true,
  });

  async function remove(id: number) {
    await api(`/watchlist/${id}`, { method: "DELETE" });
    mutate();
  }

  const grouped = GROUPS.map((g) => ({
    ...g,
    items: (data ?? []).filter((w) => g.markets.includes(w.market)),
  }));

  return (
    <div className="rounded-3xl bg-bg-1 shadow-sm">
      <div className="border-b border-bg-3 px-6 py-4">
        <h2 className="font-semibold">관심 종목</h2>
      </div>
      {!data?.length ? (
        <div className="p-8 text-center text-sm text-ink-3">
          관심 종목 없음. 종목 페이지에서 ★ 추가하세요.
        </div>
      ) : (
        <div className="divide-y divide-bg-3">
          {grouped.map((g) => (
            <WatchGroup
              key={g.key}
              title={g.label}
              items={g.items}
              onRemove={remove}
            />
          ))}
        </div>
      )}
    </div>
  );
}
