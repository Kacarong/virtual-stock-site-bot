"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { MarketStatusBar } from "@/components/MarketStatusBar";
import { PopularBoard } from "@/components/PopularBoard";
import { SearchBox } from "@/components/SearchBox";
import { api, fmtKRW, fmtNum, fmtPrice, fmtQty, fmtUSD, pctClass } from "@/lib/api";

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

const fetcher = (url: string) => api(url);

const GROUPS: { key: string; label: string; markets: string[] }[] = [
  { key: "KRX", label: "국내주식", markets: ["KRX"] },
  { key: "US", label: "해외주식", markets: ["NASDAQ", "NYSE", "AMEX"] },
  { key: "UPBIT", label: "코인", markets: ["UPBIT"] },
];

function HoldingsGroup({ title, items }: { title: string; items: Holding[] }) {
  if (items.length === 0) return null;
  const sumKrw = items.reduce((s, h) => s + Number(h.value_krw || 0), 0);
  return (
    <div>
      <div className="flex items-center justify-between px-6 py-2 text-xs text-ink-3">
        <span className="font-semibold">{title}</span>
        <span>
          {items.length}종목 · {fmtKRW(sumKrw)}
        </span>
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
                  {h.market} · {fmtQty(h.qty, h.market)}주 ·
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

export default function Home() {
  const router = useRouter();
  const { data, error, isLoading } = useSWR<Portfolio>("/portfolio", fetcher, {
    refreshInterval: 5000,
  });

  if (error?.message?.includes("401")) {
    router.replace("/login");
    return null;
  }

  if (isLoading || !data) {
    return <div className="p-8 text-sm text-ink-3">불러오는 중…</div>;
  }

  const s = data.summary;
  const grouped = GROUPS.map((g) => ({
    ...g,
    items: data.holdings.filter((h) => g.markets.includes(h.market)),
  }));

  return (
    <div className="space-y-6">
      <MarketStatusBar />
      <SearchBox />

      {/* 총자산 카드 */}
      <div className="rounded-3xl bg-white p-6 shadow-sm">
        <p className="text-xs text-ink-3">총자산 (원화 환산)</p>
        <p className="mt-1 text-3xl font-bold">{fmtKRW(s.total_assets_krw)}</p>
        <div className="mt-3 flex gap-4 text-sm">
          <span className="text-ink-3">평가손익</span>
          <span className={`font-semibold ${pctClass(s.total_pnl_pct)}`}>
            {fmtKRW(s.total_pnl_krw)} ({Number(s.total_pnl_pct).toFixed(2)}%)
          </span>
        </div>
      </div>

      {/* 현금 카드 */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-2xl bg-white p-5 shadow-sm">
          <p className="text-xs text-ink-3">현금 (원)</p>
          <p className="mt-1 text-xl font-bold">{fmtKRW(data.cash_krw)}</p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm">
          <p className="text-xs text-ink-3">현금 (달러)</p>
          <p className="mt-1 text-xl font-bold">{fmtUSD(data.cash_usd)}</p>
          <p className="mt-1 text-xs text-ink-3">USD/KRW {fmtNum(data.usdkrw, 1)}</p>
        </div>
      </div>

      {/* 실시간 인기 */}
      <PopularBoard />

      {/* 보유 종목 (시장별 그룹) */}
      <div className="rounded-3xl bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-bg-3 px-6 py-4">
          <h2 className="font-semibold">보유 종목</h2>
          <Link
            href="/holdings"
            className="text-[11px] text-ink-3 hover:text-ink-1"
          >
            전체보기 →
          </Link>
        </div>
        {data.holdings.length === 0 ? (
          <div className="p-8 text-center text-sm text-ink-3">
            보유 종목이 없습니다. 위 검색창에서 종목을 찾아 매수해보세요.
          </div>
        ) : (
          <div className="divide-y divide-bg-3">
            {grouped.map((g) => (
              <HoldingsGroup key={g.key} title={g.label} items={g.items} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
