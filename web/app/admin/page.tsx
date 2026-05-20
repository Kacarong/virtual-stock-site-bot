"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fmtKRW, fmtUSD } from "@/lib/api";

const fetcher = (u: string) => api(u);

export default function Admin() {
  const { data, mutate, error } = useSWR<any[]>("/admin/users", fetcher);
  const [sel, setSel] = useState<number | null>(null);
  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amount, setAmount] = useState("");
  const [memo, setMemo] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  if (error?.message?.includes("403")) {
    return <div className="p-8 text-center text-sm text-red-600">관리자 권한 필요</div>;
  }

  async function adjust() {
    if (!sel) return;
    setMsg(null);
    try {
      await api(`/admin/users/${sel}/cash`, {
        method: "POST",
        body: JSON.stringify({ currency, amount, memo }),
      });
      setMsg("적용됨");
      setAmount("");
      setMemo("");
      mutate();
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  async function reset(uid: number) {
    if (!confirm("이 사용자의 보유/주문을 초기화하고 자본금을 재지급할까요?")) return;
    await api(`/admin/users/${uid}/reset`, { method: "POST" });
    mutate();
  }

  async function syncSymbols() {
    setMsg("동기화 시작…");
    try {
      const r = await api<any>("/market/symbols/sync", { method: "POST" });
      setMsg(`동기화 완료: UPBIT=${r.upbit} KRX=${r.krx}`);
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">관리자</h1>
        <button
          onClick={syncSymbols}
          className="rounded-xl border border-bg-3 bg-white px-3 py-1.5 text-sm hover:bg-bg-2"
        >
          종목 마스터 수동 동기화
        </button>
      </div>

      {msg && (
        <div className="rounded-xl bg-bg-2 p-3 text-sm text-ink-2">{msg}</div>
      )}

      <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-bg-2 text-xs text-ink-3">
            <tr>
              <th className="px-4 py-2 text-left">ID</th>
              <th className="px-4 py-2 text-left">Discord</th>
              <th className="px-4 py-2 text-left">이름</th>
              <th className="px-4 py-2 text-right">KRW</th>
              <th className="px-4 py-2 text-right">USD</th>
              <th className="px-4 py-2 text-left">관리자</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id} className="border-t border-bg-3">
                <td className="px-4 py-2">{u.id}</td>
                <td className="px-4 py-2 text-xs text-ink-3">{u.discord_id}</td>
                <td className="px-4 py-2">{u.username}</td>
                <td className="px-4 py-2 text-right">{fmtKRW(u.cash_krw)}</td>
                <td className="px-4 py-2 text-right">{fmtUSD(u.cash_usd)}</td>
                <td className="px-4 py-2">{u.is_admin ? "✓" : ""}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => setSel(u.id)}
                    className="mr-2 rounded border border-bg-3 px-2 py-1 text-xs hover:bg-bg-2"
                  >
                    잔고 조정
                  </button>
                  <button
                    onClick={() => reset(u.id)}
                    className="rounded border border-bg-3 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                  >
                    초기화
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {sel && (
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <h2 className="font-semibold">사용자 #{sel} 잔고 조정</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value as any)}
              className="rounded-xl border border-bg-3 bg-white px-3 py-2 text-sm"
            >
              <option value="KRW">KRW</option>
              <option value="USD">USD</option>
            </select>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="금액 (음수=차감)"
              className="rounded-xl border border-bg-3 bg-white px-3 py-2 text-sm"
            />
          </div>
          <input
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="메모 (선택)"
            className="mt-2 w-full rounded-xl border border-bg-3 bg-white px-3 py-2 text-sm"
          />
          <div className="mt-4 flex gap-2">
            <button
              onClick={adjust}
              className="rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-fg"
            >
              적용
            </button>
            <button
              onClick={() => setSel(null)}
              className="rounded-xl border border-bg-3 px-4 py-2 text-sm"
            >
              취소
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
