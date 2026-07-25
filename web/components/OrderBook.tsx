"use client";

import useSWR from "swr";
import { api } from "@/lib/api";

type Level = { price: number; volume: number };
type Book = { asks: Level[]; bids: Level[]; currency: string | null };

const fetcher = (u: string) => api(u);

function fmtP(v: number, market: string): string {
  if (!isFinite(v)) return "-";
  if (market === "KRX" || market === "UPBIT")
    return Math.round(v).toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function OrderBook({ market, code }: { market: string; code: string }) {
  const { data } = useSWR<Book>(`/market/orderbook/${market}/${code}`, fetcher, {
    refreshInterval: 2000,
    keepPreviousData: true,
  });

  const asks = (data?.asks || []).slice(0, 8);
  const bids = (data?.bids || []).slice(0, 8);
  const maxVol = Math.max(
    1,
    ...asks.map((a) => a.volume),
    ...bids.map((b) => b.volume)
  );

  if (!data || (asks.length === 0 && bids.length === 0)) {
    return (
      <div className="rounded-2xl bg-bg-1 p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">호가</h3>
        <p className="py-8 text-center text-xs text-ink-3">호가 정보 없음</p>
      </div>
    );
  }

  const Row = ({ lv, side }: { lv: Level; side: "ask" | "bid" }) => (
    <div className="relative flex items-center justify-between px-3 py-1 text-sm">
      <div
        className={`absolute inset-y-0 ${side === "ask" ? "left-0 bg-down/10" : "right-0 bg-up/10"}`}
        style={{ width: `${(lv.volume / maxVol) * 100}%` }}
      />
      <span
        className={`relative z-10 font-medium ${side === "ask" ? "text-down" : "text-up"}`}
      >
        {fmtP(lv.price, market)}
      </span>
      <span className="relative z-10 text-xs text-ink-3">
        {lv.volume.toLocaleString()}
      </span>
    </div>
  );

  return (
    <div className="rounded-2xl bg-bg-1 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold">호가</h3>
      <div className="divide-y divide-bg-3">
        {[...asks].reverse().map((a, i) => (
          <Row key={`a${i}`} lv={a} side="ask" />
        ))}
        {bids.map((b, i) => (
          <Row key={`b${i}`} lv={b} side="bid" />
        ))}
      </div>
    </div>
  );
}
