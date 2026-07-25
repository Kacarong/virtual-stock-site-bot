"use client";

import Link from "next/link";
import useSWR from "swr";
import { api, fmtKRW } from "@/lib/api";

type Row = {
  rank: number;
  user_id: number;
  username: string;
  avatar_url: string | null;
  total_assets_krw: string;
  cash_krw: string;
  holdings_krw: string;
};

const fetcher = (u: string) => api(u);

const MEDALS = ["🥇", "🥈", "🥉"];

export default function RankingPage() {
  const { data, isLoading } = useSWR<Row[]>("/portfolio/ranking", fetcher, {
    refreshInterval: 10000,
  });

  return (
    <div className="space-y-4">
      <div>
        <Link href="/" className="text-xs text-ink-3 hover:text-ink-1">
          ← 대시보드
        </Link>
        <h1 className="mt-1 text-2xl font-bold">자산 랭킹</h1>
        <p className="mt-1 text-xs text-ink-3">
          총자산(현금+평가금) 원화 환산 기준 · 10초마다 갱신
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
              <li
                key={r.user_id}
                className="flex items-center gap-4 px-6 py-4"
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
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
