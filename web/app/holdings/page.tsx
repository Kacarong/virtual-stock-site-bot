"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtKRW, fmtPrice, fmtQty, pctClass } from "@/lib/api";

type Holding = {
  symbol_id: number;
  code: string;
  name: string;
  market: string;
  currency: string;
  qty: string;
  avg_cost: string;
  price: string;
  value: string;
  value_krw: string;
  pnl: string;
  pnl_pct: string;
};

type Portfolio = {
  cash_krw: string;
  cash_usd: string;
  usdkrw: string;
  holdings: Holding[];
  summary: {
    total_value_krw: string;
    total_cost_krw: string;
    total_pnl_krw: string;
    total_pnl_pct: string;
    total_assets_krw: string;
  };
};

type Realized = {
  period: "all" | "daily" | "monthly";
  total_krw: string;
  items: { bucket: string; realized_krw: string }[];
};

type Period = "all" | "daily" | "monthly";

const fetcher = (u: string) => api(u);

const GROUPS: { key: string; label: string; markets: string[] }[] = [
  { key: "KRX", label: "국내주식", markets: ["KRX"] },
  { key: "US", label: "해외주식", markets: ["NASDAQ", "NYSE", "AMEX"] },
  { key: "UPBIT", label: "코인", markets: ["UPBIT"] },
];

function GroupSection({ title, items }: { title: string; items: Holding[] }) {
  if (items.length === 0) return null;
  const sumKrw = items.reduce((s, h) => s + Number(h.value_krw || 0), 0);
  return (
    <div className="rounded-3xl bg-bg-1 shadow-sm">
      <div className="flex items-center justify-between border-b border-bg-3 px-6 py-3">
        <h3 className="font-semibold">{title}</h3>
        <div className="text-xs text-ink-3">
          {items.length}종목 · 평가 {fmtKRW(sumKrw)}
        </div>
      </div>
      <ul className="divide-y divide-bg-3">
        {items.map((h) => (
          <li key={h.symbol_id}>
            <Link
              href={`/symbols/${h.market}/${encodeURIComponent(h.code)}`}
              className="flex items-center justify-between px-6 py-3 hover:bg-bg-2"
            >
              <div>
                <div className="font-semibold">{h.name}</div>
                <div className="text-[11px] text-ink-3">
                  {h.market} · {h.code} · {fmtQty(h.qty, h.market)}주 ·
                  평균 {fmtPrice(h.avg_cost, h.market, h.currency)}
                </div>
              </div>
              <div className="text-right">
                <div className="font-semibold">
                  {fmtPrice(h.value, h.market, h.currency)}
                </div>
                <div className={`text-[11px] ${pctClass(h.pnl_pct)}`}>
                  {Number(h.pnl_pct) >= 0 ? "+" : ""}
                  {Number(h.pnl_pct).toFixed(2)}%
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RealizedCard() {
  const [period, setPeriod] = useState<Period>("all");
  const { data, isLoading } = useSWR<Realized>(
    `/portfolio/realized?period=${period}`,
    fetcher,
    { refreshInterval: 30000 }
  );

  const total = data ? Number(data.total_krw) : 0;
  return (
    <div className="rounded-3xl bg-bg-1 p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">실현손익</h3>
        <div className="flex gap-1">
          {(
            [
              { k: "all", l: "전체" },
              { k: "monthly", l: "월별" },
              { k: "daily", l: "일별" },
            ] as { k: Period; l: string }[]
          ).map((p) => (
            <button
              key={p.k}
              onClick={() => setPeriod(p.k)}
              className={`rounded-full px-2.5 py-0.5 text-[11px] ${
                period === p.k
                  ? "bg-ink-1 text-white"
                  : "bg-bg-2 text-ink-3 hover:bg-bg-3"
              }`}
            >
              {p.l}
            </button>
          ))}
        </div>
      </div>
      <p className={`mt-2 text-2xl font-bold ${pctClass(total)}`}>
        {total >= 0 ? "+" : ""}
        {fmtKRW(total)}
      </p>
      <p className="text-[11px] text-ink-3">
        매도 시점에 확정된 손익 누계 (원화 환산)
      </p>

      {period !== "all" && (
        <div className="mt-4">
          {isLoading ? (
            <p className="text-xs text-ink-3">불러오는 중…</p>
          ) : !data?.items.length ? (
            <p className="text-xs text-ink-3">기록이 없습니다.</p>
          ) : (
            <ul className="max-h-64 divide-y divide-bg-3 overflow-y-auto rounded-xl border border-bg-3">
              {data.items.map((it) => {
                const n = Number(it.realized_krw);
                return (
                  <li
                    key={it.bucket}
                    className="flex items-center justify-between px-3 py-2 text-xs"
                  >
                    <span className="text-ink-2">{it.bucket}</span>
                    <span className={`font-semibold ${pctClass(n)}`}>
                      {n >= 0 ? "+" : ""}
                      {fmtKRW(n)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function HoldingsPage() {
  const { data, isLoading } = useSWR<Portfolio>("/portfolio", fetcher, {
    refreshInterval: 5000,
  });

  if (isLoading || !data) {
    return <div className="p-8 text-sm text-ink-3">불러오는 중…</div>;
  }

  const s = data.summary;
  const grouped = GROUPS.map((g) => ({
    ...g,
    items: data.holdings.filter((h) => g.markets.includes(h.market)),
  }));

  // 시장별 평가/매수 합계 (원화 환산)
  const marketSummary = grouped.map((g) => {
    const items = g.items;
    const valueKrw = items.reduce((s, h) => s + Number(h.value_krw || 0), 0);
    // 매수금 KRW 환산 (USD면 현재 환율)
    const rate = Number(data.usdkrw) || 1;
    const costKrw = items.reduce((s, h) => {
      const cost = Number(h.avg_cost) * Number(h.qty);
      return s + (h.currency === "USD" ? cost * rate : cost);
    }, 0);
    const pnlKrw = valueKrw - costKrw;
    const pnlPct = costKrw > 0 ? (pnlKrw / costKrw) * 100 : 0;
    return { ...g, valueKrw, costKrw, pnlKrw, pnlPct };
  });

  return (
    <div className="space-y-4">
      <div>
        <Link href="/" className="text-xs text-ink-3 hover:text-ink-1">
          ← 대시보드
        </Link>
        <h1 className="mt-1 text-2xl font-bold">보유종목</h1>
      </div>

      {/* 평가손익 요약 */}
      <div className="rounded-3xl bg-bg-1 p-5 shadow-sm">
        <p className="text-xs text-ink-3">총 평가 (원화 환산)</p>
        <p className="mt-1 text-2xl font-bold">{fmtKRW(s.total_value_krw)}</p>
        <p className={`mt-1 text-sm ${pctClass(s.total_pnl_pct)}`}>
          평가손익 {fmtKRW(s.total_pnl_krw)} (
          {Number(s.total_pnl_pct).toFixed(2)}%)
        </p>

        {/* 시장별 등락률 */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          {marketSummary.map((m) => (
            <div key={m.key} className="rounded-xl bg-bg-2 p-3">
              <p className="text-[10px] text-ink-3">{m.label}</p>
              <p className="mt-0.5 text-xs font-semibold">
                {fmtKRW(m.valueKrw)}
              </p>
              <p
                className={`text-[10px] font-semibold ${pctClass(m.pnlPct)}`}
              >
                {m.items.length === 0
                  ? "-"
                  : `${m.pnlPct >= 0 ? "+" : ""}${m.pnlPct.toFixed(2)}%`}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* 실현손익 */}
      <RealizedCard />

      {data.holdings.length === 0 ? (
        <div className="rounded-3xl bg-bg-1 p-8 text-center text-sm text-ink-3 shadow-sm">
          보유 종목이 없습니다.
        </div>
      ) : (
        <div className="space-y-4">
          {grouped.map((g) => (
            <GroupSection key={g.key} title={g.label} items={g.items} />
          ))}
        </div>
      )}
    </div>
  );
}
