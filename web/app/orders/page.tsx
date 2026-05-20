"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fmtNum, pctClass } from "@/lib/api";

const fetcher = (u: string) => api(u);

export default function Orders() {
  const [tab, setTab] = useState<"pending" | "all" | "trades">("pending");
  const { data: orders, mutate } = useSWR<any[]>(
    tab === "trades" ? null : `/orders?${tab === "pending" ? "status=PENDING" : ""}`,
    fetcher,
    { refreshInterval: 3000 }
  );
  const { data: trades } = useSWR<any[]>(
    tab === "trades" ? "/orders/trades" : null,
    fetcher,
    { refreshInterval: 5000 }
  );

  async function cancel(id: number) {
    if (!confirm(`주문 #${id} 취소?`)) return;
    try {
      await api(`/orders/${id}`, { method: "DELETE" });
      mutate();
    } catch (e: any) {
      alert(e.message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {([
          ["pending", "대기 주문"],
          ["all", "전체 주문"],
          ["trades", "체결 내역"],
        ] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded-xl px-4 py-2 text-sm ${
              tab === k ? "bg-brand text-brand-fg" : "bg-bg-2 text-ink-2"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "trades" ? (
        <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
          {!trades?.length ? (
            <div className="p-8 text-center text-sm text-ink-3">체결 내역 없음</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-bg-2 text-xs text-ink-3">
                <tr>
                  <th className="px-4 py-2 text-left">시각</th>
                  <th className="px-4 py-2 text-left">종목</th>
                  <th className="px-4 py-2 text-left">구분</th>
                  <th className="px-4 py-2 text-right">가격</th>
                  <th className="px-4 py-2 text-right">수량</th>
                  <th className="px-4 py-2 text-right">수수료</th>
                  <th className="px-4 py-2 text-right">세금</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-t border-bg-3">
                    <td className="px-4 py-2 text-xs text-ink-3">
                      {new Date(t.executed_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">{t.name}</td>
                    <td className={`px-4 py-2 ${t.side === "BUY" ? "text-up" : "text-down"}`}>
                      {t.side === "BUY" ? "매수" : "매도"}
                    </td>
                    <td className="px-4 py-2 text-right">{fmtNum(t.price, 2)}</td>
                    <td className="px-4 py-2 text-right">{fmtNum(t.qty, 8)}</td>
                    <td className="px-4 py-2 text-right text-ink-3">
                      {fmtNum(t.fee, 2)}
                    </td>
                    <td className="px-4 py-2 text-right text-ink-3">
                      {fmtNum(t.tax, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
          {!orders?.length ? (
            <div className="p-8 text-center text-sm text-ink-3">주문 없음</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-bg-2 text-xs text-ink-3">
                <tr>
                  <th className="px-4 py-2 text-left">시각</th>
                  <th className="px-4 py-2 text-left">종목</th>
                  <th className="px-4 py-2 text-left">구분</th>
                  <th className="px-4 py-2 text-left">유형</th>
                  <th className="px-4 py-2 text-right">수량</th>
                  <th className="px-4 py-2 text-right">지정가</th>
                  <th className="px-4 py-2 text-left">상태</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-t border-bg-3">
                    <td className="px-4 py-2 text-xs text-ink-3">
                      {new Date(o.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-2">{o.name}</td>
                    <td className={`px-4 py-2 ${o.side === "BUY" ? "text-up" : "text-down"}`}>
                      {o.side === "BUY" ? "매수" : "매도"}
                    </td>
                    <td className="px-4 py-2 text-ink-3">{o.order_type}</td>
                    <td className="px-4 py-2 text-right">{fmtNum(o.qty, 8)}</td>
                    <td className="px-4 py-2 text-right">
                      {o.limit_price ? fmtNum(o.limit_price, 2) : "-"}
                    </td>
                    <td className="px-4 py-2">{o.status}</td>
                    <td className="px-4 py-2 text-right">
                      {o.status === "PENDING" && (
                        <button
                          onClick={() => cancel(o.id)}
                          className="rounded border border-bg-3 px-2 py-1 text-xs hover:bg-bg-2"
                        >
                          취소
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
