"use client";

import useSWR from "swr";
import { api, fmtSmart } from "@/lib/api";

type Trade = { price: number; volume: number; timestamp: string | null };

const fetcher = (u: string) => api(u);

function fmtP(v: number, market: string): string {
  if (!isFinite(v)) return "-";
  if (market === "UPBIT") return fmtSmart(v); // 코인은 가격대별 소수점 (1원 미만 코인이 0으로 보이던 문제)
  if (market === "KRX") return Math.round(v).toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

// 코인 수량은 크기별 소수점 (기본 3자리면 0.0001 BTC가 0으로 보인다)
function fmtV(v: number, market: string): string {
  return market === "UPBIT" ? fmtSmart(v) : v.toLocaleString();
}

function fmtT(ts: string | null): string {
  if (!ts) return "-";
  try {
    return new Date(ts).toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "-";
  }
}

export function RecentTrades({
  market,
  code,
}: {
  market: string;
  code: string;
}) {
  const { data } = useSWR<Trade[]>(
    `/market/trades/${market}/${code}?count=30`,
    fetcher,
    { refreshInterval: 2000, keepPreviousData: true }
  );
  const trades = data || [];

  return (
    <div className="rounded-2xl bg-bg-1 p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold">실시간 체결</h3>
      {trades.length === 0 ? (
        <p className="py-8 text-center text-xs text-ink-3">체결 내역 없음</p>
      ) : (
        <div className="thin-scroll max-h-72 overflow-y-auto pr-2">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-bg-1 text-xs text-ink-3">
              <tr>
                <th className="py-1 text-left font-normal">시각</th>
                <th className="py-1 text-right font-normal">체결가</th>
                <th className="py-1 text-right font-normal">체결량</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t, i) => {
                const prev = trades[i + 1]?.price;
                const cls =
                  prev == null
                    ? "text-ink-1"
                    : t.price > prev
                    ? "text-up"
                    : t.price < prev
                    ? "text-down"
                    : "text-ink-1";
                return (
                  <tr key={i} className="border-t border-bg-3">
                    <td className="py-1 text-xs text-ink-3">
                      {fmtT(t.timestamp)}
                    </td>
                    <td className={`py-1 text-right font-medium ${cls}`}>
                      {fmtP(t.price, market)}
                    </td>
                    <td className="py-1 text-right text-ink-3">
                      {fmtV(t.volume, market)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
