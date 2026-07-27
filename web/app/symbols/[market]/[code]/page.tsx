"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Chart } from "@/components/Chart";
import { OrderBook } from "@/components/OrderBook";
import { RecentTrades } from "@/components/RecentTrades";
import { FxModal } from "@/components/FxModal";
import { api, fmtPrice, fmtQty, pctClass } from "@/lib/api";
import { useUsdToKrw } from "@/lib/useUsdToKrw";

type Quote = {
  market: string;
  code: string;
  name: string;
  symbol_id: number | null;
  currency: string;
  price: string;
  prev_close: string | null;
};

type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type MarketStatus = {
  [m: string]: {
    open: boolean;
    next_open: string | null;
    session?: string | null;
  };
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
    refreshInterval: 15000,
    keepPreviousData: true,
  });
  const { data: watchlist, mutate: mutateWatch } = useSWR<any[]>(
    "/watchlist",
    fetcher,
    { refreshInterval: 30000 }
  );
  const sym = hits?.find((h: any) => h.market === market && h.code === code);
  const isOpen = mstatus?.[market]?.open ?? (market === "UPBIT");
  const nextOpen = mstatus?.[market]?.next_open;
  const session = mstatus?.[market]?.session;

  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT" | "SCHEDULED">(
    "MARKET"
  );
  const [qty, setQty] = useState("1");
  const [limitPrice, setLimitPrice] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // 미국주식 원화 보기 토글 (대시보드와 공유)
  const isUS = market === "NASDAQ" || market === "NYSE" || market === "AMEX";
  const [showKrw, setShowKrw] = useUsdToKrw();
  const [fxOpen, setFxOpen] = useState(false);
  // 포트폴리오 — 환율 + 현재 종목 보유 수량(전량매도용) + 현금 잔액
  const { data: pf, mutate: mutatePf } = useSWR<{
    usdkrw: string;
    cash_krw: string;
    cash_usd: string;
    holdings: { symbol_id: number; code: string; market: string; qty: string }[];
  }>("/portfolio", fetcher, { refreshInterval: 10000 });
  const rate = pf?.usdkrw ? Number(pf.usdkrw) : null;
  const myHolding = pf?.holdings?.find(
    (h) => h.market === market && h.code === code
  );
  const holdingQty = myHolding ? Number(myHolding.qty) : 0;

  useEffect(() => {
    if (q?.price && !limitPrice) {
      const n = Number(q.price);
      setLimitPrice(isFinite(n) ? String(n) : q.price);
    }
  }, [q?.price]);

  // 시장 닫혀있으면 자동으로 예약주문 모드
  useEffect(() => {
    if (!isOpen && orderType === "MARKET") setOrderType("SCHEDULED");
  }, [isOpen]);

  async function submit() {
    setMsg(null);
    setErr(null);
    // symbol_id 우선순위: quote 응답 → search 결과
    const symbolId = q?.symbol_id ?? sym?.id;
    if (!symbolId) {
      setErr("종목 정보를 찾는 중입니다. 잠시 후 다시 시도하세요.");
      return;
    }
    try {
      const body: any = {
        symbol_id: symbolId,
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

  const symbolIdAny = q?.symbol_id ?? sym?.id;
  const isWatched = !!(
    symbolIdAny && watchlist?.find((w: any) => w.symbol_id === symbolIdAny)
  );

  async function toggleWatch() {
    if (!symbolIdAny) return;
    setMsg(null);
    setErr(null);
    try {
      if (isWatched) {
        await api(`/watchlist/${symbolIdAny}`, { method: "DELETE" });
        setMsg("관심종목에서 제거됨");
      } else {
        await api(`/watchlist/${symbolIdAny}`, { method: "POST" });
        setMsg("관심종목에 추가됨 ⭐");
      }
      mutateWatch();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  // 코인은 실시간 스트림(SSE)으로 현재가 갱신 → 헤더/차트/주문 모두 실시간
  const [coinLive, setCoinLive] = useState<number | null>(null);
  useEffect(() => {
    setCoinLive(null);
    if (market !== "UPBIT") return;
    const es = new EventSource("/api/market/stream/coin");
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        const entry = d[code];
        if (entry && typeof entry.price === "number") setCoinLive(entry.price);
      } catch {}
    };
    return () => es.close();
  }, [market, code]);

  const rawPrice = q?.price ? Number(q.price) : null;
  const price =
    market === "UPBIT" && coinLive !== null ? coinLive : rawPrice;
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
      <div className="rounded-3xl bg-bg-1 p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-ink-3">
              {market} · {code}
            </p>
            <h1 className="mt-1 text-2xl font-bold">{displayName}</h1>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  isOpen
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                ● {session || (isOpen ? "거래가능" : "거래불가")}
              </span>
              {isUS && rate && (
                <>
                  <div className="flex gap-0.5">
                    <button
                      onClick={() => setShowKrw(false)}
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        !showKrw ? "bg-ink-1 text-bg-1" : "bg-bg-2 text-ink-3"
                      }`}
                    >
                      $
                    </button>
                    <button
                      onClick={() => setShowKrw(true)}
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        showKrw ? "bg-ink-1 text-bg-1" : "bg-bg-2 text-ink-3"
                      }`}
                    >
                      ₩
                    </button>
                  </div>
                  <button
                    onClick={() => setFxOpen(true)}
                    className="rounded-full bg-brand/10 px-2.5 py-0.5 text-[10px] font-semibold text-brand hover:bg-brand/20"
                  >
                    환전
                  </button>
                </>
              )}
            </div>
            {price !== null && (
              <p className="mt-2 text-3xl font-bold">
                {fmtPrice(
                  isUS && showKrw && rate ? price * rate : price,
                  isUS && showKrw && rate ? "KRX" : market,
                  isUS && showKrw && rate ? "KRW" : (sym?.currency || q?.currency)
                )}
              </p>
            )}
            {change !== null && changePct !== null && (
              <p
                className={`mt-1 text-sm font-semibold ${pctClass(
                  changePct.toString()
                )}`}
              >
                {change >= 0 ? "+" : ""}
                {fmtPrice(
                  isUS && showKrw && rate ? change * rate : change,
                  isUS && showKrw && rate ? "KRX" : market,
                  isUS && showKrw && rate ? "KRW" : (sym?.currency || q?.currency)
                )}{" "}
                ({changePct.toFixed(2)}%)
              </p>
            )}
          </div>
          <button
            onClick={toggleWatch}
            title={isWatched ? "관심종목에서 제거" : "관심종목에 추가"}
            className={`rounded-xl border px-3 py-1.5 text-sm transition ${
              isWatched
                ? "border-yellow-300 bg-yellow-50 text-yellow-700"
                : "border-bg-3 hover:bg-bg-2 text-ink-2"
            }`}
          >
            {isWatched ? "★ 관심 등록됨" : "☆ 관심 추가"}
          </button>
        </div>
      </div>

      {/* 차트 · 호가 · 주문 3열 (Toss 스타일) */}
      <div className="grid gap-4 xl:grid-cols-[2.3fr_1fr_1fr]">
        {/* 차트 */}
        <div className="min-w-0 rounded-3xl bg-bg-1 p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap gap-1">
            {TFS.map((iv) => (
              <button
                key={iv.key}
                onClick={() => setTf(iv.key)}
                className={`rounded-full px-3 py-1 text-xs ${
                  tf === iv.key
                    ? "bg-ink-1 text-bg-1"
                    : "bg-bg-2 text-ink-3 hover:bg-bg-3"
                }`}
              >
                {iv.label}
              </button>
            ))}
          </div>
          {candles && candles.length > 0 ? (
            <Chart
              data={candles}
              priceScale={isUS && showKrw && rate ? rate : 1}
              unitLabel={
                isUS
                  ? showKrw && rate
                    ? "원"
                    : "달러"
                  : market === "UPBIT" || market === "KRX"
                  ? "원"
                  : undefined
              }
              integerOnly={
                market === "KRX" || (isUS && showKrw && !!rate)
              }
              livePrice={price ?? undefined}
              intervalSec={
                tf === "1m"
                  ? 60
                  : tf === "5m"
                  ? 300
                  : tf === "1h"
                  ? 3600
                  : undefined
              }
            />
          ) : (
            <div className="grid h-[360px] place-items-center text-sm text-ink-3">
              차트 데이터를 불러오는 중…
            </div>
          )}
        </div>

        {/* 호가 */}
        <OrderBook market={market} code={code} />

        {/* 주문 */}
        <div className="min-w-0 rounded-3xl bg-bg-1 p-6 shadow-sm">
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

        {holdingQty > 0 && (
          <div className="mt-3 flex items-center justify-between rounded-xl bg-bg-2 px-4 py-2 text-xs">
            <span className="text-ink-3">
              보유 {fmtQty(holdingQty, market)}주
            </span>
            <button
              onClick={() => {
                setSide("SELL");
                setQty(String(holdingQty));
              }}
              className="rounded-lg bg-down px-3 py-1 font-semibold text-white"
            >
              전량매도
            </button>
          </div>
        )}

        {/* 25%/50%/100% 비율 버튼 — 매수=현금기준, 매도=보유수량기준 */}
        {(() => {
          const refPrice = (() => {
            if (orderType === "LIMIT" && limitPrice) {
              const lp = Number(limitPrice);
              if (isFinite(lp) && lp > 0) return lp;
            }
            return q?.price ? Number(q.price) : 0;
          })();
          const isUpbit = market === "UPBIT";
          // 매수 가능 금액 (해당 종목 통화 기준)
          const cashKrw = pf?.cash_krw ? Number(pf.cash_krw) : 0;
          const cashUsd = pf?.cash_usd ? Number(pf.cash_usd) : 0;
          const buyCash = isUS ? cashUsd : cashKrw;
          const canBuy = refPrice > 0 && buyCash > 0;
          const canSell = holdingQty > 0;
          const active = side === "BUY" ? canBuy : canSell;
          if (!active) return null;
          const apply = (pct: number) => {
            if (side === "BUY") {
              const raw = (buyCash * pct) / 100 / refPrice;
              if (!isFinite(raw) || raw <= 0) return;
              setQty(isUpbit ? raw.toFixed(8).replace(/\.?0+$/, "") : String(Math.floor(raw)));
            } else {
              const raw = (holdingQty * pct) / 100;
              if (!isFinite(raw) || raw <= 0) return;
              setQty(isUpbit ? raw.toFixed(8).replace(/\.?0+$/, "") : String(Math.floor(raw)));
            }
          };
          return (
            <div className="mt-3 flex gap-1.5">
              {[25, 50, 100].map((p) => (
                <button
                  key={p}
                  onClick={() => apply(p)}
                  className={`flex-1 rounded-lg py-2 text-xs font-semibold ${
                    side === "BUY"
                      ? "bg-up/10 text-up hover:bg-up/20"
                      : "bg-down/10 text-down hover:bg-down/20"
                  }`}
                >
                  {p === 100 ? (side === "BUY" ? "전량매수" : "전량매도") : `${p}%`}
                </button>
              ))}
            </div>
          );
        })()}

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
                orderType === t
                  ? "bg-brand text-brand-fg"
                  : "bg-bg-2 text-ink-2"
              }`}
            >
              {t === "MARKET" ? "시장가" : t === "LIMIT" ? "지정가" : "예약주문"}
            </button>
          ))}
        </div>

        {orderType === "SCHEDULED" && (
          <p className="mt-2 rounded-lg border border-brand/30 bg-brand/10 p-2 text-[11px] text-brand">
            시장 마감 중입니다. 개장 직후 자동 체결되도록 예약됩니다.
          </p>
        )}

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs text-ink-3">수량</label>
            <input
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className="mt-1 w-full rounded-xl border border-bg-3 bg-bg-1 px-4 py-3 text-sm outline-none focus:border-brand"
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
                className="mt-1 w-full rounded-xl border border-bg-3 bg-bg-1 px-4 py-3 text-sm outline-none focus:border-brand"
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
          <p className="mt-3 rounded bg-green-500/10 p-3 text-xs text-green-500">
            {msg}
          </p>
        )}
        {err && (
          <p className="mt-3 rounded bg-red-500/10 p-3 text-xs text-red-500">
            {err}
          </p>
        )}
        </div>
      </div>

      {/* 실시간 체결 */}
      <RecentTrades market={market} code={code} />

      {fxOpen && pf && rate && (
        <FxModal
          cashKrw={pf.cash_krw}
          cashUsd={pf.cash_usd}
          rate={rate}
          onClose={() => setFxOpen(false)}
          onDone={() => mutatePf()}
        />
      )}
    </div>
  );
}
