"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Chart } from "@/components/Chart";
import { api, fmtNum, pctClass } from "@/lib/api";

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

const fetcher = (u: string) => api(u);

export default function SymbolPage({
  params,
}: {
  params: { market: string; code: string };
}) {
  const { market, code: rawCode } = params;
  const code = decodeURIComponent(rawCode);

  const [tf, setTf] = useState<"1m" | "5m" | "1h" | "1d">("1d");

  const { data: q } = useSWR<Quote>(`/market/quote/${market}/${code}`, fetcher, {
    refreshInterval: 3000,
  });
  const { data: candles } = useSWR<Candle[]>(
    `/market/history/${market}/${code}?interval=${tf}`,
    fetcher,
    { refreshInterval: tf === "1m" ? 10000 : 60000 }
  );
  const { data: hits } = useSWR<any[]>(
    `/market/search?q=${encodeURIComponent(code)}`,
    fetcher
  );
  const sym = hits?.find((h: any) => h.market === market && h.code === code);

  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("MARKET");
  const [qty, setQty] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (q?.price && !limitPrice) setLimitPrice(q.price);
  }, [q?.price]);

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
      const r = await api<any>("/orders", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMsg(
        `주문 #${r.id} ${r.status === "FILLED" ? "체결" : "접수"} (${r.qty}주)`
      );
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

  return (
    <div className="space-y-6">
      <div className="rounded-3xl bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-ink-3">
              {market} · {code}
            </p>
            <h1 className="mt-1 text-2xl font-bold">{q?.name || code}</h1>
            {price !== null && (
              <p className="mt-2 text-3xl font-bold">
                {fmtNum(price, 2)}
                {sym?.currency === "USD" ? " USD" : " KRW"}
              </p>
            )}
            {change !== null && changePct !== null && (
              <p
                className={`mt-1 text-sm font-semibold ${pctClass(
                  changePct.toString()
                )}`}
              >
                {change >= 0 ? "+" : ""}
                {fmtNum(change, 2)} ({changePct.toFixed(2)}%)
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
          <div className="mb-3 flex gap-1">
            {(["1m", "5m", "1h", "1d"] as const).map((iv) => (
              <button
                key={iv}
                onClick={() => setTf(iv)}
                className={`rounded-full px-3 py-1 text-xs ${
                  tf === iv
                    ? "bg-ink-1 text-white"
                    : "bg-bg-2 text-ink-3 hover:bg-bg-3"
                }`}
              >
                {iv === "1d" ? "일봉" : iv === "1h" ? "1시간" : iv === "5m" ? "5분" : "1분"}
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
        <h2 className="font-semibold">주문하기</h2>

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
          {(["MARKET", "LIMIT"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setOrderType(t)}
              className={`flex-1 rounded-lg py-2 text-sm ${
                orderType === t ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-2"
              }`}
            >
              {t === "MARKET" ? "시장가" : "지정가"}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-ink-3">수량</label>
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="mt-1 w-full rounded-xl border border-bg-3 bg-white px-4 py-3 text-sm outline-none focus:border-brand"
            />
          </div>
          {orderType === "LIMIT" && (
            <div>
              <label className="text-xs text-ink-3">지정가</label>
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
          {side === "BUY" ? "매수 주문" : "매도 주문"}
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
