"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { FxModal } from "@/components/FxModal";
import { api, fmtKRW, fmtPrice, fmtUSD, pctClass } from "@/lib/api";

type Holding = {
  symbol_id: number;
  code: string;
  name: string;
  market: string;
  currency: string;
  value: string;
  pnl_pct: string;
};

type Portfolio = {
  cash_krw: string;
  cash_usd: string;
  usdkrw: string;
  holdings: Holding[];
  summary: {
    total_assets_krw: string;
    total_pnl_krw: string;
    total_pnl_pct: string;
  };
};

const fetcher = (u: string) => api(u);

export function MyInvestmentPanel() {
  const { data, error, mutate } = useSWR<Portfolio>("/portfolio", fetcher, {
    refreshInterval: 5000,
    shouldRetryOnError: false,
  });
  const { data: pending } = useSWR<any[]>("/orders?status=PENDING", fetcher, {
    refreshInterval: 5000,
    shouldRetryOnError: false,
  });
  const [fxOpen, setFxOpen] = useState(false);

  // 미로그인(401) 등 → 패널 숨김
  if (error) return null;
  if (!data)
    return (
      <div className="rounded-2xl bg-bg-1 p-5 text-sm text-ink-3 shadow-sm">
        내 투자 불러오는 중…
      </div>
    );

  const s = data.summary;
  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-bg-1 p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">내 투자</h3>
          <button
            onClick={() => setFxOpen(true)}
            className="rounded-lg bg-bg-2 px-2.5 py-1 text-xs text-ink-2 hover:bg-bg-3"
          >
            환전
          </button>
        </div>
        <p className="mt-3 text-2xl font-bold">{fmtKRW(s.total_assets_krw)}</p>
        <p className={`text-sm ${pctClass(s.total_pnl_pct)}`}>
          평가손익 {fmtKRW(s.total_pnl_krw)} ({Number(s.total_pnl_pct).toFixed(2)}
          %)
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-bg-2 p-3">
            <p className="text-[11px] text-ink-3">원화</p>
            <p className="text-sm font-semibold">{fmtKRW(data.cash_krw)}</p>
          </div>
          <div className="rounded-xl bg-bg-2 p-3">
            <p className="text-[11px] text-ink-3">달러</p>
            <p className="text-sm font-semibold">{fmtUSD(data.cash_usd)}</p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl bg-bg-1 p-4 shadow-sm">
        <h4 className="mb-2 text-sm font-semibold">보유 종목</h4>
        {data.holdings.length === 0 ? (
          <p className="py-6 text-center text-xs text-ink-3">
            보유 종목이 없어요
          </p>
        ) : (
          <ul className="divide-y divide-bg-3">
            {data.holdings.slice(0, 8).map((h) => (
              <li key={h.symbol_id}>
                <Link
                  href={`/symbols/${h.market}/${encodeURIComponent(h.code)}`}
                  className="flex items-center justify-between py-2 hover:opacity-80"
                >
                  <span className="min-w-0 truncate text-sm">{h.name}</span>
                  <span className="ml-2 shrink-0 text-right">
                    <span className="block text-sm font-medium">
                      {fmtPrice(h.value, h.market, h.currency)}
                    </span>
                    <span className={`block text-[11px] ${pctClass(h.pnl_pct)}`}>
                      {Number(h.pnl_pct) >= 0 ? "+" : ""}
                      {Number(h.pnl_pct).toFixed(2)}%
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-2xl bg-bg-1 p-4 shadow-sm">
        <h4 className="mb-2 text-sm font-semibold">주문내역</h4>
        {!pending?.length ? (
          <p className="py-6 text-center text-xs text-ink-3">
            대기중인 주문이 없어요
          </p>
        ) : (
          <ul className="divide-y divide-bg-3">
            {pending.slice(0, 6).map((o) => (
              <li
                key={o.id}
                className="flex items-center justify-between py-2 text-sm"
              >
                <span className="min-w-0 truncate">{o.name}</span>
                <span
                  className={
                    o.side === "BUY" ? "shrink-0 text-up" : "shrink-0 text-down"
                  }
                >
                  {o.side === "BUY" ? "매수" : "매도"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {fxOpen && (
        <FxModal
          cashKrw={data.cash_krw}
          cashUsd={data.cash_usd}
          rate={Number(data.usdkrw) || 1}
          onClose={() => setFxOpen(false)}
          onDone={() => mutate()}
        />
      )}
    </div>
  );
}
