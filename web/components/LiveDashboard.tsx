"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api, fmtSmart } from "@/lib/api";
import { useUsdToKrw } from "@/lib/useUsdToKrw";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  value: number | null;
  market_cap?: number | null;
  symbol_id?: number | null;
  industry?: string | null;
  buy_ratio?: number | null;
};

type Indicator = {
  key: string;
  label: string;
  price: number;
  change_pct: number;
  spark: number[];
  currency: string;
};

type MarketKey = "KRX" | "US" | "UPBIT";
type Sort =
  | "value"
  | "volume"
  | "change"
  | "decline"
  | "market_cap"
  | "toss_value"
  | "toss_volume";

// 코인(UPBIT)에는 없는 정렬 (Toss 미지원 / 시총 미지원)
const NON_UPBIT_SORTS = ["market_cap", "toss_value", "toss_volume"];

const fetcher = (u: string) => api(u);

const MARKETS: { key: MarketKey; label: string }[] = [
  { key: "KRX", label: "국내" },
  { key: "US", label: "해외" },
  { key: "UPBIT", label: "코인" },
];

const SORTS: { key: Sort; label: string }[] = [
  { key: "toss_value", label: "토스 거래대금" },
  { key: "toss_volume", label: "토스 거래량" },
  { key: "value", label: "거래대금" },
  { key: "volume", label: "거래량" },
  { key: "change", label: "급상승" },
  { key: "decline", label: "급하락" },
  { key: "market_cap", label: "시가총액" },
];

const UP = "#FF4D4D";
const DOWN = "#3182F6";

function fmtCompact(n?: number | null): string {
  if (n == null) return "-";
  const v = Number(n);
  if (!isFinite(v) || v <= 0) return "-";
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toFixed(1) + "조";
  if (a >= 1e8) return (v / 1e8).toFixed(1) + "억";
  if (a >= 1e4) return (v / 1e4).toFixed(1) + "만";
  return Math.round(v).toLocaleString();
}

function fmtPriceCell(
  row: Row,
  showKrw: boolean,
  rate: number | null
): string {
  const v = row.price;
  if (v == null) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  const isUS =
    row.market === "NASDAQ" || row.market === "NYSE" || row.market === "AMEX";
  if (isUS && showKrw && rate)
    return Math.round(n * rate).toLocaleString() + "원";
  // 코인은 1원 미만 소액도 소수점까지 표시 (가격대별 자동)
  if (row.market === "UPBIT") return fmtSmart(n) + "원";
  if (row.market === "KRX") return Math.round(n).toLocaleString() + "원";
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pctText(n?: number | null): { t: string; c: string } {
  if (n == null || !isFinite(Number(n))) return { t: "-", c: "text-ink-3" };
  const v = Number(n);
  const sign = v > 0 ? "+" : "";
  const c = v > 0 ? "text-up" : v < 0 ? "text-down" : "text-ink-3";
  return { t: `${sign}${v.toFixed(2)}%`, c };
}

function Spark({ data }: { data: number[] }) {
  if (!data || data.length < 2) return null;
  const w = 96;
  const h = 34;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const rng = max - min || 1;
  const up = data[data.length - 1] >= data[0];
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / rng) * h}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline
        points={pts}
        fill="none"
        stroke={up ? UP : DOWN}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// 가격(trigger) 변동 시 등락률 셀에 배경 플래시. 색은 틱 방향이 아니라
// 현재 등락률 부호(양수=빨강, 음수=파랑)를 따른다.
function PctFlash({
  trigger,
  changePct,
  text,
  colorClass,
}: {
  trigger: number | null | undefined;
  changePct: number | null | undefined;
  text: string;
  colorClass: string;
}) {
  const prev = useRef<number | null | undefined>(trigger);
  const [n, setN] = useState(0);
  useEffect(() => {
    const p = prev.current;
    if (p != null && trigger != null && trigger !== p) {
      setN((x) => x + 1);
    }
    prev.current = trigger;
  }, [trigger]);
  const flashClass =
    n === 0
      ? ""
      : changePct != null && changePct < 0
      ? "flash-down"
      : "flash-up";
  return (
    <div className="text-right">
      <span
        key={n}
        className={`inline-block rounded px-1.5 py-0.5 font-medium ${colorClass} ${flashClass}`}
      >
        {text}
      </span>
    </div>
  );
}

function Logo({ row }: { row: Row }) {
  const [err, setErr] = useState(false);
  const url = `https://static.toss.im/png-icons/securities/icn-sec-fill-${row.code}.png`;
  if (err)
    return (
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-bg-3 text-[11px] text-ink-2">
        {row.name.slice(0, 1)}
      </div>
    );
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      width={28}
      height={28}
      className="h-7 w-7 shrink-0 rounded-full bg-white object-contain"
      onError={() => setErr(true)}
    />
  );
}

function IndicatorBar() {
  const { data } = useSWR<Indicator[]>("/market/indicators", fetcher, {
    refreshInterval: 15000,
    keepPreviousData: true,
  });
  const items = data || [];
  if (items.length === 0) return null;
  return (
    <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((it) => {
        const p = pctText(it.change_pct);
        const priceStr =
          it.currency === "USD"
            ? it.price.toLocaleString(undefined, { maximumFractionDigits: 2 })
            : Math.round(it.price).toLocaleString();
        return (
          <div
            key={it.key}
            className="flex items-center justify-between rounded-2xl border border-bg-3 bg-bg-1 px-5 py-4"
          >
            <div>
              <div className="text-sm text-ink-3">{it.label}</div>
              <div className="mt-1 text-xl font-bold text-ink-1">{priceStr}</div>
              <div className={`mt-0.5 text-sm ${p.c}`}>{p.t}</div>
            </div>
            <Spark data={it.spark} />
          </div>
        );
      })}
    </div>
  );
}

export function LiveDashboard() {
  const router = useRouter();
  const [market, setMarket] = useState<MarketKey>("KRX");
  const [sort, setSort] = useState<Sort>("toss_value");
  // 해외주식 원화/달러 표시 토글 (기본 원화, 페이지 간 공유)
  const [showKrw, setShowKrw] = useUsdToKrw();
  const { data: fx } = useSWR<{ usdkrw: string }>(
    market === "US" ? "/portfolio" : null,
    fetcher,
    { shouldRetryOnError: false }
  );
  const rate = fx?.usdkrw ? Number(fx.usdkrw) : null;

  // 코인 실시간 스트림 (SSE) — 코인 탭에서만 구독, code→{price,change_pct} 덮어쓰기
  const [live, setLive] = useState<
    Record<string, { price: number; change_pct: number }>
  >({});
  useEffect(() => {
    if (market !== "UPBIT") {
      setLive({});
      return;
    }
    const es = new EventSource("/api/market/stream/coin");
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        setLive((prev) => ({ ...prev, ...d }));
      } catch {}
    };
    return () => es.close();
  }, [market]);

  const sortsForMarket = SORTS.filter(
    (s) => !(market === "UPBIT" && NON_UPBIT_SORTS.includes(s.key))
  );

  const { data, error, isLoading } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=100`,
    fetcher,
    {
      refreshInterval: (latest) =>
        !latest || latest.length === 0 ? 2000 : 2000,
      keepPreviousData: true,
    }
  );

  const { data: watched, mutate: mutateWatch } = useSWR<any[]>(
    "/watchlist",
    fetcher,
    { shouldRetryOnError: false }
  );
  const watchedSet = new Set((watched || []).map((w) => w.symbol_id));

  async function toggleWatch(
    e: React.MouseEvent,
    symbolId?: number | null
  ) {
    e.preventDefault();
    e.stopPropagation();
    if (!symbolId) return;
    try {
      if (watchedSet.has(symbolId))
        await api(`/watchlist/${symbolId}`, { method: "DELETE" });
      else await api(`/watchlist/${symbolId}`, { method: "POST" });
      mutateWatch();
    } catch {}
  }

  if (error?.message?.includes("401")) {
    router.replace("/login");
    return null;
  }

  // keepPreviousData 때문에 시장 탭을 바꿔도 이전 시장 데이터가 잠깐 남는다.
  // 현재 선택한 시장에 속한 행만 표시 → "탭 바꿔도 그대로" 방지(전환 중엔 로딩 표시).
  const marketMatches = (rowMarket: string, sel: MarketKey) => {
    if (sel === "US")
      return (
        rowMarket === "NASDAQ" ||
        rowMarket === "NYSE" ||
        rowMarket === "AMEX"
      );
    if (sel === "UPBIT") return rowMarket === "UPBIT";
    return rowMarket === "KRX";
  };
  const allRows = data || [];
  const rows = allRows.filter((r) => marketMatches(r.market, market));
  // data는 있는데 선택 시장과 안 맞으면 = 탭 전환 직후 새 데이터 대기 중
  const transitioning = allRows.length > 0 && rows.length === 0;

  // 코인은 시가총액·산업 컬럼 제외 → 그리드 트랙도 시장별로 다르게
  const isUpbit = market === "UPBIT";
  const gridCols = isUpbit
    ? "grid-cols-[28px_32px_1fr_110px_90px] sm:grid-cols-[28px_32px_1fr_120px_90px_110px] lg:grid-cols-[28px_32px_1fr_120px_90px_110px_120px]"
    : "grid-cols-[28px_32px_1fr_110px_90px_100px] sm:grid-cols-[28px_32px_1fr_120px_90px_110px_110px] lg:grid-cols-[28px_32px_1fr_120px_90px_110px_110px_120px] xl:grid-cols-[28px_32px_1fr_120px_90px_110px_110px_120px_130px]";

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-1">실시간 차트</h1>
      </div>

      <IndicatorBar />

      {/* 시장 탭 */}
      <div className="mb-3 flex gap-2">
        {MARKETS.map((m) => (
          <button
            key={m.key}
            onClick={() => {
              setMarket(m.key);
              if (m.key === "UPBIT" && NON_UPBIT_SORTS.includes(sort))
                setSort("value");
            }}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
              market === m.key
                ? "bg-ink-1 text-bg-1"
                : "bg-bg-3 text-ink-3 hover:text-ink-1"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* 정렬 칩 + (해외) 원화/달러 토글 */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-2">
        {sortsForMarket.map((s) => (
          <button
            key={s.key}
            onClick={() => setSort(s.key)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              sort === s.key
                ? "bg-bg-3 text-ink-1"
                : "bg-bg-1 text-ink-3 hover:text-ink-2"
            }`}
          >
            {s.label}
          </button>
        ))}
        </div>
        {market === "US" && (
          <div className="flex gap-1">
            <button
              onClick={() => setShowKrw(true)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                showKrw ? "bg-ink-1 text-bg-1" : "bg-bg-1 text-ink-3"
              }`}
            >
              원화
            </button>
            <button
              onClick={() => setShowKrw(false)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                !showKrw ? "bg-ink-1 text-bg-1" : "bg-bg-1 text-ink-3"
              }`}
            >
              달러
            </button>
          </div>
        )}
      </div>

      {/* 랭킹 테이블 */}
      <div className="overflow-hidden rounded-2xl border border-bg-3 bg-bg-1">
        <div className={`grid ${gridCols} items-center gap-2 border-b border-bg-3 px-4 py-3 text-xs text-ink-3`}>
          <div />
          <div>순위</div>
          <div>종목</div>
          <div className="text-right">현재가</div>
          <div className="text-right">등락률</div>
          <div className="hidden text-right sm:block">거래대금</div>
          {!isUpbit && <div className="text-right">시가총액</div>}
          <div className="hidden text-center lg:block">거래 비율</div>
          {!isUpbit && <div className="hidden xl:block">산업</div>}
        </div>

        {(isLoading || transitioning) && rows.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-3">
            불러오는 중…
          </div>
        )}
        {!isLoading && !transitioning && rows.length === 0 && (
          <div className="px-4 py-10 text-center text-sm text-ink-3">
            데이터가 없습니다. (Toss 허용 IP 등록을 확인해 주세요)
          </div>
        )}

        {rows.map((row, i) => {
          // 코인은 실시간 스트림(live) 값으로 현재가/등락률 덮어쓰기
          const lv = isUpbit ? live[row.code] : undefined;
          const dispRow = lv ? { ...row, price: lv.price } : row;
          const p = pctText(lv ? lv.change_pct : row.change_pct);
          return (
            <Link
              key={`${row.market}-${row.code}`}
              href={`/symbols/${row.market}/${encodeURIComponent(row.code)}`}
              className={`grid ${gridCols} items-center gap-2 border-b border-bg-3 px-4 py-3 text-sm transition last:border-0 hover:bg-bg-2`}
            >
              <span
                role="button"
                onClick={(e) => toggleWatch(e, row.symbol_id)}
                className={`cursor-pointer text-center text-base leading-none ${
                  row.symbol_id && watchedSet.has(row.symbol_id)
                    ? "text-up"
                    : "text-ink-4 hover:text-up"
                }`}
              >
                {row.symbol_id && watchedSet.has(row.symbol_id) ? "♥" : "♡"}
              </span>
              <div className="text-ink-3">{i + 1}</div>
              <div className="flex min-w-0 items-center gap-2.5">
                <Logo row={row} />
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink-1">
                    {row.name}
                  </div>
                  <div className="text-[11px] text-ink-3">{row.code}</div>
                </div>
              </div>
              <div className="text-right font-medium text-ink-1">
                {fmtPriceCell(dispRow, showKrw, rate)}
              </div>
              <PctFlash
                key={`${market}-${sort}`}
                trigger={dispRow.price ?? null}
                changePct={lv ? lv.change_pct : row.change_pct}
                text={p.t}
                colorClass={p.c}
              />
              <div className="hidden text-right text-ink-3 sm:block">
                {fmtCompact(row.value)}
              </div>
              {!isUpbit && (
                <div className="text-right text-ink-3">
                  {fmtCompact(row.market_cap)}
                </div>
              )}
              <div className="hidden lg:block">
                {typeof row.buy_ratio === "number" ? (
                  <div className="flex items-center gap-1">
                    <span className="w-5 text-right text-[10px] font-medium text-up">
                      {Math.round(row.buy_ratio * 100)}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-down/40">
                      <div
                        className="h-full rounded-full bg-up"
                        style={{ width: `${row.buy_ratio * 100}%` }}
                      />
                    </div>
                    <span className="w-5 text-[10px] font-medium text-down">
                      {100 - Math.round(row.buy_ratio * 100)}
                    </span>
                  </div>
                ) : (
                  <div className="text-center text-[11px] text-ink-4">-</div>
                )}
              </div>
              {!isUpbit && (
                <div className="hidden xl:block">
                  {row.industry ? (
                    <span className="inline-block truncate rounded bg-bg-3 px-2 py-0.5 text-[11px] text-ink-2">
                      {row.industry}
                    </span>
                  ) : null}
                </div>
              )}
            </Link>
          );
        })}
      </div>

      <p className="mt-4 text-center text-xs text-ink-4">
        시세·랭킹·로고 제공: 토스증권 · 5초마다 자동 갱신
      </p>
    </div>
  );
}
