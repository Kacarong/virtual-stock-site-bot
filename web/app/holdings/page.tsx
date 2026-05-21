"use client";

import Link from "next/link";
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
    total_pnl_krw: string;
    total_pnl_pct: string;
    total_assets_krw: string;
  };
};

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
    <div className="rounded-3xl bg-white shadow-sm">
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

  return (
    <div className="space-y-4">
      <div>
        <Link href="/" className="text-xs text-ink-3 hover:text-ink-1">
          ← 대시보드
        </Link>
        <h1 className="mt-1 text-2xl font-bold">보유종목</h1>
      </div>

      <div className="rounded-3xl bg-white p-5 shadow-sm">
        <p className="text-xs text-ink-3">총 평가 (원화 환산)</p>
        <p className="mt-1 text-2xl font-bold">{fmtKRW(s.total_value_krw)}</p>
        <p className={`mt-1 text-sm ${pctClass(s.total_pnl_pct)}`}>
          평가손익 {fmtKRW(s.total_pnl_krw)} ({Number(s.total_pnl_pct).toFixed(2)}%)
        </p>
      </div>

      {data.holdings.length === 0 ? (
        <div className="rounded-3xl bg-white p-8 text-center text-sm text-ink-3 shadow-sm">
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
