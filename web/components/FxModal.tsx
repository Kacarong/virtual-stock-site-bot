"use client";

import { useMemo, useState } from "react";
import { api, fmtKRW, fmtUSD } from "@/lib/api";

type Props = {
  cashKrw: string;
  cashUsd: string;
  rate: number;
  onClose: () => void;
  onDone: () => void;
};

type Dir = "KRW_TO_USD" | "USD_TO_KRW";

const SPREAD = 0.01; // 백엔드와 동일 1%

export function FxModal({ cashKrw, cashUsd, rate, onClose, onDone }: Props) {
  const [dir, setDir] = useState<Dir>("KRW_TO_USD");
  const [amount, setAmount] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const krw = Number(cashKrw);
  const usd = Number(cashUsd);

  // 예상 수령액 (스프레드 1% 불리하게)
  const preview = useMemo(() => {
    const n = Number(amount);
    if (!isFinite(n) || n <= 0) return null;
    if (dir === "KRW_TO_USD") {
      const eff = rate * (1 + SPREAD);
      return { recv: n / eff, recvLabel: "USD" as const };
    } else {
      const eff = rate * (1 - SPREAD);
      return { recv: n * eff, recvLabel: "KRW" as const };
    }
  }, [amount, dir, rate]);

  function setMax() {
    if (dir === "KRW_TO_USD") setAmount(String(Math.floor(krw)));
    else setAmount(String(Math.floor(usd * 100) / 100));
  }

  function setPct(p: number) {
    if (dir === "KRW_TO_USD") setAmount(String(Math.floor(krw * p)));
    else setAmount(String(Math.floor(usd * p * 100) / 100));
  }

  async function submit() {
    setErr(null);
    setMsg(null);
    const n = Number(amount);
    if (!isFinite(n) || n <= 0) {
      setErr("환전할 금액을 입력하세요.");
      return;
    }
    setBusy(true);
    try {
      const r = await api<any>("/portfolio/fx", {
        method: "POST",
        body: JSON.stringify({ direction: dir, amount: String(n) }),
      });
      if (dir === "KRW_TO_USD") {
        setMsg(`${fmtKRW(r.paid_krw)} → ${fmtUSD(r.received_usd)} 환전 완료`);
      } else {
        setMsg(`${fmtUSD(r.paid_usd)} → ${fmtKRW(r.received_krw)} 환전 완료`);
      }
      setAmount("");
      onDone();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-3xl bg-bg-1 p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold">환전</h3>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-ink-3 hover:bg-bg-2"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        <p className="mt-1 text-[11px] text-ink-3">
          현재 환율 1 USD = {rate.toLocaleString()} 원 · 스프레드 1%
        </p>

        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            onClick={() => {
              setDir("KRW_TO_USD");
              setAmount("");
            }}
            className={`rounded-xl py-3 text-sm font-semibold ${
              dir === "KRW_TO_USD" ? "bg-ink-1 text-bg-1" : "bg-bg-2 text-ink-2"
            }`}
          >
            원 → 달러
          </button>
          <button
            onClick={() => {
              setDir("USD_TO_KRW");
              setAmount("");
            }}
            className={`rounded-xl py-3 text-sm font-semibold ${
              dir === "USD_TO_KRW" ? "bg-ink-1 text-bg-1" : "bg-bg-2 text-ink-2"
            }`}
          >
            달러 → 원
          </button>
        </div>

        <div className="mt-4 rounded-2xl bg-bg-2 p-3 text-xs">
          <div className="flex justify-between text-ink-3">
            <span>보유 원화</span>
            <span className="font-semibold text-ink-1">{fmtKRW(krw)}</span>
          </div>
          <div className="mt-1 flex justify-between text-ink-3">
            <span>보유 달러</span>
            <span className="font-semibold text-ink-1">{fmtUSD(usd)}</span>
          </div>
        </div>

        <div className="mt-4">
          <label className="text-xs text-ink-3">
            {dir === "KRW_TO_USD" ? "보낼 원화 (KRW)" : "보낼 달러 (USD)"}
          </label>
          <input
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0"
            className="mt-1 w-full rounded-xl border border-bg-3 bg-bg-1 px-4 py-3 text-sm outline-none focus:border-brand"
          />
          <div className="mt-2 flex gap-1">
            {[0.25, 0.5, 1].map((p) => (
              <button
                key={p}
                onClick={() => (p === 1 ? setMax() : setPct(p))}
                className="flex-1 rounded-lg bg-bg-2 py-1.5 text-[11px] text-ink-2 hover:bg-bg-3"
              >
                {p === 1 ? "전액" : `${p * 100}%`}
              </button>
            ))}
          </div>
        </div>

        {preview && (
          <div className="mt-3 rounded-xl bg-brand/5 px-4 py-3 text-sm">
            <span className="text-ink-3">받을 금액 </span>
            <span className="font-bold text-brand">
              {preview.recvLabel === "USD"
                ? fmtUSD(preview.recv)
                : fmtKRW(preview.recv)}
            </span>
          </div>
        )}

        {err && (
          <p className="mt-3 rounded bg-red-50 p-2 text-xs text-red-700">{err}</p>
        )}
        {msg && (
          <p className="mt-3 rounded bg-green-50 p-2 text-xs text-green-700">{msg}</p>
        )}

        <button
          onClick={submit}
          disabled={busy}
          className="mt-5 w-full rounded-2xl bg-brand py-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? "처리 중…" : "환전하기"}
        </button>
      </div>
    </div>
  );
}
