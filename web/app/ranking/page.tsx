"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { api, fmtKRW, fmtPrice, fmtQty, pctClass } from "@/lib/api";

type Row = {
  rank: number;
  user_id: number;
  username: string;
  avatar_url: string | null;
  total_assets_krw: string;
  cash_krw: string;
  holdings_krw: string;
};

type DetailHolding = {
  symbol_id: number;
  code: string;
  name: string;
  market: string;
  currency: string;
  qty: string;
  avg_cost: string;
  price: string;
  value_krw: string;
  pnl_krw: string;
  pnl_pct: string;
};

type Detail = {
  user_id: number;
  username: string;
  avatar_url: string | null;
  holdings_value_krw: string;
  holdings_pnl_krw: string;
  holdings_pnl_pct: string;
  holdings: DetailHolding[];
};

const fetcher = (u: string) => api(u);

const MEDALS = ["🥇", "🥈", "🥉"];

function pnlSign(v: string | number): string {
  return Number(v) >= 0 ? "+" : "";
}

function DetailModal({
  userId,
  onClose,
}: {
  userId: number;
  onClose: () => void;
}) {
  const { data, isLoading } = useSWR<Detail>(
    `/portfolio/ranking/${userId}`,
    fetcher,
    { refreshInterval: 10000 }
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-bg-1 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            {data?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={data.avatar_url}
                alt={data.username}
                className="h-10 w-10 rounded-full"
              />
            ) : (
              <div className="h-10 w-10 rounded-full bg-bg-3" />
            )}
            <div>
              <div className="font-bold">{data?.username ?? "…"}</div>
              <div className="text-[11px] text-ink-3">보유 종목 상세</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-ink-3 hover:bg-bg-2"
          >
            ✕
          </button>
        </div>

        {data && (
          <div className="mt-4 flex gap-3 rounded-2xl bg-bg-2 px-4 py-3 text-sm">
            <div className="flex-1">
              <div className="text-[11px] text-ink-3">평가금</div>
              <div className="font-semibold">
                {fmtKRW(data.holdings_value_krw)}
              </div>
            </div>
            <div className="flex-1">
              <div className="text-[11px] text-ink-3">평가손익</div>
              <div
                className={`font-semibold ${pctClass(data.holdings_pnl_krw)}`}
              >
                {pnlSign(data.holdings_pnl_krw)}
                {fmtKRW(data.holdings_pnl_krw)} ({pnlSign(data.holdings_pnl_pct)}
                {data.holdings_pnl_pct}%)
              </div>
            </div>
          </div>
        )}

        <div className="mt-4">
          {isLoading && !data ? (
            <div className="p-6 text-center text-sm text-ink-3">불러오는 중…</div>
          ) : !data?.holdings?.length ? (
            <div className="p-6 text-center text-sm text-ink-3">
              보유 종목이 없습니다.
            </div>
          ) : (
            <ul className="divide-y divide-bg-3">
              {data.holdings.map((h) => (
                <li key={h.symbol_id}>
                  <Link
                    href={`/symbols/${h.market}/${encodeURIComponent(h.code)}`}
                    className="flex items-center gap-3 py-3 hover:bg-bg-2"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {h.name}
                      </div>
                      <div className="text-[11px] text-ink-3">
                        {fmtQty(h.qty, h.market)}주 · 평단{" "}
                        {fmtPrice(h.avg_cost, h.market, h.currency)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold">
                        {fmtKRW(h.value_krw)}
                      </div>
                      <div className={`text-[11px] ${pctClass(h.pnl_krw)}`}>
                        {pnlSign(h.pnl_krw)}
                        {fmtKRW(h.pnl_krw)} ({pnlSign(h.pnl_pct)}
                        {h.pnl_pct}%)
                      </div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RankingPage() {
  const { data, isLoading } = useSWR<Row[]>("/portfolio/ranking", fetcher, {
    refreshInterval: 10000,
  });
  const [sel, setSel] = useState<number | null>(null);

  return (
    <div className="space-y-4">
      <div>
        <Link href="/" className="text-xs text-ink-3 hover:text-ink-1">
          ← 대시보드
        </Link>
        <h1 className="mt-1 text-2xl font-bold">자산 랭킹</h1>
        <p className="mt-1 text-xs text-ink-3">
          총자산(현금+평가금) 원화 환산 기준 · 10초마다 갱신 · 유저를 누르면 보유
          종목을 볼 수 있어요
        </p>
      </div>

      <div className="rounded-3xl bg-bg-1 shadow-sm">
        {isLoading && !data ? (
          <div className="p-8 text-center text-sm text-ink-3">불러오는 중…</div>
        ) : !data?.length ? (
          <div className="p-8 text-center text-sm text-ink-3">데이터 없음</div>
        ) : (
          <ul className="divide-y divide-bg-3">
            {data.map((r) => (
              <li key={r.user_id}>
                <button
                  onClick={() => setSel(r.user_id)}
                  className="flex w-full items-center gap-4 px-6 py-4 text-left hover:bg-bg-2"
                >
                  <div className="w-10 text-center text-lg font-bold">
                    {r.rank <= 3 ? MEDALS[r.rank - 1] : `${r.rank}`}
                  </div>
                  {r.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={r.avatar_url}
                      alt={r.username}
                      className="h-10 w-10 rounded-full"
                    />
                  ) : (
                    <div className="h-10 w-10 rounded-full bg-bg-3" />
                  )}
                  <div className="flex-1">
                    <div className="font-semibold">{r.username}</div>
                    <div className="text-[11px] text-ink-3">
                      현금 {fmtKRW(r.cash_krw)} · 보유 {fmtKRW(r.holdings_krw)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold">
                      {fmtKRW(r.total_assets_krw)}
                    </div>
                    <div className="text-[11px] text-ink-3">상세 보기 →</div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {sel !== null && <DetailModal userId={sel} onClose={() => setSel(null)} />}
    </div>
  );
}
