"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Chart } from "@/components/Chart";
import { api, fmtPrice, fmtQty, pctClass } from "@/lib/api";

type Quote = {
  market: string;
  code: string;
  name: string;
  price: string;
  prev_close: string | null;
};

type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

type MarketStatus = {
  [m: string]: { open: boolean; next_open: string | null };
};

const fetcher = (u: string) => api(u);

type TF = "1m" | "5m" | "1h" | "1d" | "1w" | "1mo" | "all";
const TFS: { key: TF; label: string }[] = [
  { key: "1m", label: "1분" },
  { key: "5m", label: "5분" },
  { key: "1h", label: "1시간" },
  { key: "1d", label: "일봉" },
  { key: "1w", label: "주봉" },
  { key: "1mo", label: "월봉" },
  { key: "all", label: "전체" },
];

export default function SymbolPage({
  params,
}: {
  params: { market: string; code: string };
}) {
  const { market, code: rawCode } = params;
  const code = decodeURIComponent(rawCode);

  const [tf, setTf] = useState<TF>("1d");

  const { data: q } = useSWR<Quote>(`/market/quote/${market}/${code}`, fetcher, {
    refreshInterval: 3000,
    keepPreviousData: true,
  });
  const { data: candles } = useSWR<Candle[]>(
    `/market/history/${market}/${code}?interval=${tf}`,
    fetcher,
    { refreshInterval: tf === "1m" ? 10000 : 60000, keepPreviousData: true }
  );
  const { data: hits } = useSWR<any[]>(
    `/market/search?q=${encodeURIComponent(code)}`,
    fetcher
  );
  const { data: mstatus } = useSWR<MarketStatus>("/market/status", fetcher, {
    refreshInterval: 60000,
  });
  const sym = hits?.find((h: any) => h.market === market && h.code === code);
  const isOpen = mstatus?.[market]?.open ?? (market === "UPBIT");
  const nextOpen = mstatus?.[market]?.next_open;

  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "SCHEDULED">(
    "MARKET"
  );
  const [qty, setQty] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (q?.price && !limitPrice) setLimitPrice(q.price);
  }, [q?.price]);

  // 시장 닫혀있으면 자동으로 예약주문 모드
  useEffect(() => {
    if (!isOpen && orderType === "MARKET") setOrderType("SCHEDULED");
  }, [isOpen]);

  async function submit() {
    setMsg(null);
    setErr(null);
    if (!sym) {
      setErr("종목 정보를 찾는 중입니다. 잠시 후 다시 시도하세요.");
      return;
    }
    try {
      const body: any = {
        symbol_id: sym.id,
        side,
        order_type: orderType,
        qty,
      };
      if (orderType === "LIMIT") body.limit_price = limitPrice;
      if (orderType === "SCHEDULED") {
        body.limit_price = limitPrice || q?.price;
        body.scheduled_at = nextOpen;
      }
      const r = await api<any>("/orders", {
        method: "POST",
        body: JSON.stringify(body),
      });
      const sideKo = side === "BUY" ? "매수" : "매도";
      const stateKo =
        r.status === "FILLED"
          ? "체결됨"
          : r.status === "PENDING" && orderType === "SCHEDULED"
          ? "예약 완료"
          : "접수됨";
      const qStr = fmtQty(r.qty, market);
      setMsg(`${r.name || code} ${sideKo} ${qStr}주 — ${stateKo}`);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function watchAdd() {
    if (!sym) return;
    await api(`/watchlist/${sym.id}`, { method: "POST" });
    setMsg("관심종목에 추가됨");
  }

  const price = q?.price ? Number(q.price) : null;
  const prev = q?.prev_close ? Number(q.prev_close) : null;
  const change = price !== null && prev !== null ? price - prev : null;
  const changePct = change !== null && prev ? (change / prev) * 100 : null;

  // 종목명: 한글 우선 — quote/hit 중 영문/code가 아닌 것 선택
  function pickName(n: string | undefined | null): boolean {
    if (!n) return false;
    if (n === code) return false;
    return true;
  }
  // 한글 포함 여부
  const hasHangul = (s: string) => /[\u3131-\uD79D]/.test(s);
  const candidates = [q?.name, sym?.name].filter(pickName) as string[];
  const hangul = candidates.find(hasHangul);
  const displayName = hangul || candidates[0] || code;

  return (
    <div className="space-y-6">
      <div className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-ink-3">
              {market} · {code}
            </p>
            <h1 className="mt-1 text-2xl font-bold">{displayName}</h1>
            <div className="mt-1">
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  isOpen
                    ? "bg-up/10 text-up"
                    : "bg-bg-3 text-ink-3"
                }`}
              >
                {isOpen ? "● 거래가능" : "○ 거래불가"}
              </span>
            </div>
            {price !== null && (
              <p className="mt-2 text-3xl font-bold">
                {fmtPrice(price, market, sym?.currency)}
              </p>
            )}
            {change !== null && changePct !== null && (
              <p
                className={`mt-1 text-sm font-semibold ${pctClass(
                  changePct.toString()
                )}`}
              >
                {change >= 0 ? "+" : ""}
                {fmtPrice(change, market, sym?.currency)} ({changePct.toFixed(2)}%)
              </p>
            )}
          </div>
          <button
            onClick={watchAdd}
            className="rounded-xl border border-bg-3 px-3 py-1.5 text-sm hover:bg-bg-2"
          >
            ★ 관심 추가
          </button>
        </div>

        <div className="mt-6">
          <div className="mb-3 flex flex-wrap gap-1">
            {TFS.map((iv) => (
              <button
                key={iv.key}
                onClick={() => setTf(iv.key)}
                className={`rounded-full px-3 py-1 text-xs ${
                  tf === iv.key
                    ? "bg-ink-1 text-white"
                    : "bg-bg-2 text-ink-3 hover:bg-bg-3"
                }`}
              >
                {iv.label}
              </button>
            ))}
          </div>
          {candles && candles.length > 0 ? (
            <Chart data={candles} />
          ) : (
            <div className="grid h-[360px] place-items-center text-sm text-ink-3">
              차트 데이터를 불러오는 중…
            </div>
          )}
        </div>
      </div>

      {/* 주문 패널 */}
      <div className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">주문하기</h2>
          {!isOpen && nextOpen && (
            <span className="text-[11px] text-ink-3">
              다음 개장: {new Date(nextOpen).toLocaleString("ko-KR")}
            </span>
          )}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2">
          {(["BUY", "SELL"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSide(s)}
              className={`rounded-xl py-3 text-sm font-semibold ${
                side === s
                  ? s === "BUY"
                    ? "bg-up text-white"
                    : "bg-down text-white"
                  : "bg-bg-2 text-ink-2"
              }`}
            >
              {s === "BUY" ? "매수" : "매도"}
            </button>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
          {(
            isOpen
              ? (["MARKET", "LIMIT"] as const)
              : (["SCHEDULED", "LIMIT"] as const)
          ).map((t) => (
            <button
              key={t}
              onClick={() => setOrderType(t)}
              className={`flex-1 rounded-lg py-2 text-sm ${
                orderType === t ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-2"
              }`}
            >
              {t === "MARKET" ? "시장가" : t === "LIMIT" ? "지정가" : "예약주문"}
            </button>
          ))}
        </div>

        {orderType === "SCHEDULED" && (
          <p className="mt-2 rounded bg-yellow-50 p-2 text-[11px] text-yellow-700">
            시장 마감 중입니다. 개장 직후 자동 체결되도록 예약됩니다.
          </p>
        )}

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-ink-3">수량</label>
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="mt-1 w-full rounded-xl border border-bg-3 bg-white px-4 py-3 text-sm outline-none focus:border-brand"
            />
          </div>
          {(orderType === "LIMIT" || orderType === "SCHEDULED") && (
            <div>
              <label className="text-xs text-ink-3">
                {orderType === "SCHEDULED" ? "예상 체결가 (지정가)" : "지정가"}
              </label>
              <input
                value={limitPrice}
                onChange={(e) => setLimitPrice(e.target.value)}
                className="mt-1 w-full rounded-xl border border-bg-3 bg-white px-4 py-3 text-sm outline-none focus:border-brand"
              />
            </div>
          )}
        </div>

        <button
          onClick={submit}
          className={`mt-5 w-full rounded-2xl py-3 text-sm font-semibold text-white ${
            side === "BUY" ? "bg-up" : "bg-down"
          }`}
        >
          {orderType === "SCHEDULED"
            ? `${side === "BUY" ? "예약 매수" : "예약 매도"}`
            : `${side === "BUY" ? "매수 주문" : "매도 주문"}`}
        </button>

        {msg && (
          <p className="mt-3 rounded bg-green-50 p-3 text-xs text-green-700">{msg}</p>
        )}
        {err && (
          <p className="mt-3 rounded bg-red-50 p-3 text-xs text-red-700">{err}</p>
        )}
      </div>
    </div>
  );
}
