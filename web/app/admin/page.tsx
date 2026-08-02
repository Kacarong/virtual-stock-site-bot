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

  // 지원금 지급 폼
  const [grantTitle, setGrantTitle] = useState("");
  const [grantMsg, setGrantMsg] = useState("");
  const [grantAmount, setGrantAmount] = useState("");
  const [granting, setGranting] = useState(false);

  if (error?.message?.includes("403")) {
    return <div className="p-8 text-center text-sm text-red-600">관리자 권한 필요</div>;
  }

  async function grant() {
    if (!grantTitle.trim() || !Number(grantAmount)) {
      setMsg("지원금 제목과 금액을 입력하세요.");
      return;
    }
    if (
      !confirm(
        `모든 유저에게 ${Number(grantAmount).toLocaleString()}원 지원금을 지급할까요?`
      )
    )
      return;
    setGranting(true);
    setMsg(null);
    try {
      const r = await api<any>("/support/grant", {
        method: "POST",
        body: JSON.stringify({
          title: grantTitle.trim(),
          message: grantMsg.trim() || null,
          amount_krw: grantAmount,
        }),
      });
      setMsg(
        `지원금 지급 완료: ${r.granted_count}명에게 ${Number(
          r.amount_krw
        ).toLocaleString()}원`
      );
      setGrantTitle("");
      setGrantMsg("");
      setGrantAmount("");
      mutate();
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setGranting(false);
    }
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
      setMsg(`동기화 완료: UPBIT=${r.upbit} KRX=${r.krx} US=${r.us ?? 0}`);
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
          className="rounded-xl border border-bg-3 bg-bg-1 px-3 py-1.5 text-sm hover:bg-bg-2"
        >
          종목 마스터 수동 동기화
        </button>
      </div>

      {msg && (
        <div className="rounded-xl bg-bg-2 p-3 text-sm text-ink-2">{msg}</div>
      )}

      {/* 지원금 지급 — 모든 유저에게 현금 + 입장 알림 */}
      <div className="rounded-2xl bg-bg-1 p-6 shadow-sm">
        <h2 className="font-semibold">🎁 전체 유저 지원금 지급</h2>
        <p className="mt-1 text-xs text-ink-3">
          모든 유저에게 원화 지원금을 지급하고, 각 유저 입장 시 알림을 띄웁니다.
          유저는 알림을 끌 수 있고, 수익 탭에 &quot;지원금&quot;으로 표기됩니다.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <input
            value={grantTitle}
            onChange={(e) => setGrantTitle(e.target.value)}
            placeholder="알림 제목 (예: 여름 이벤트 지원금)"
            className="rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
          />
          <input
            value={grantAmount}
            onChange={(e) => setGrantAmount(e.target.value)}
            placeholder="지급 금액 (원)"
            inputMode="numeric"
            className="rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
          />
        </div>
        <textarea
          value={grantMsg}
          onChange={(e) => setGrantMsg(e.target.value)}
          placeholder="알림 설명 (선택) — 유저에게 보여줄 안내 문구"
          rows={2}
          className="mt-3 w-full rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
        />
        <button
          onClick={grant}
          disabled={granting}
          className="mt-3 rounded-xl bg-brand px-4 py-2 text-sm font-semibold text-brand-fg disabled:opacity-50"
        >
          {granting ? "지급 중…" : "전체 유저에게 지원금 지급"}
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl bg-bg-1 shadow-sm">
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
        <div className="rounded-2xl bg-bg-1 p-6 shadow-sm">
          <h2 className="font-semibold">사용자 #{sel} 잔고 조정</h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value as any)}
              className="rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
            >
              <option value="KRW">KRW</option>
              <option value="USD">USD</option>
            </select>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="금액 (음수=차감)"
              className="rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
            />
          </div>
          <input
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="메모 (선택)"
            className="mt-2 w-full rounded-xl border border-bg-3 bg-bg-1 px-3 py-2 text-sm"
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
