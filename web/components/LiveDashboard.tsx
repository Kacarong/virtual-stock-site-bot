"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";

type Row = {
  market: string;
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  volume: number | null;
  value: number | null;
  market_cap?: number | null;
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
type Sort = "value" | "volume" | "change" | "decline" | "market_cap";

const fetcher = (u: string) => api(u);

const MARKETS: { key: MarketKey; label: string }[] = [
  { key: "KRX", label: "국내" },
  { key: "US", label: "해외" },
  { key: "UPBIT", label: "코인" },
];

const SORTS: { key: Sort; label: string }[] = [
  { key: "value", label: "거래대금" },
  { key: "volume", label: "거래량" },
  { key: "change", label: "급상승" },
  { key: "decline", label: "급하락" },
  { key: "market_cap", label: "시가총액" },
];

const UP = "#F5475B";
const DOWN = "#4C82FB";

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

function fmtPriceCell(row: Row): string {
  const v = row.price;
  if (v == null) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  if (row.market === "KRX" || row.market === "UPBIT")
    return Math.round(n).toLocaleString() + "원";
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function pctText(n?: number | null): { t: string; c: string } {
  if (n == null || !isFinite(Number(n))) return { t: "-", c: "text-gray-500" };
  const v = Number(n);
  const sign = v > 0 ? "+" : "";
  const c = v > 0 ? "text-[#F5475B]" : v < 0 ? "text-[#4C82FB]" : "text-gray-400";
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

function Logo({ row }: { row: Row }) {
  const [err, setErr] = useState(false);
  const url = `https://static.toss.im/png-icons/securities/icn-sec-fill-${row.code}.png`;
  if (err)
    return (
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#2b2f36] text-[11px] text-gray-300">
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
            className="flex items-center justify-between rounded-2xl border border-[#23262d] bg-[#16181d] px-5 py-4"
          >
            <div>
              <div className="text-sm text-gray-400">{it.label}</div>
              <div className="mt-1 text-xl font-bold text-white">{priceStr}</div>
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
  const [sort, setSort] = useState<Sort>("value");

  // 다크 대시보드: 뷰포트 전체를 어둡게 (마운트 동안만)
  useEffect(() => {
    const prev = document.body.style.background;
    document.body.style.background = "#0f1115";
    return () => {
      document.body.style.background = prev;
    };
  }, []);

  const sortsForMarket = SORTS.filter(
    (s) => !(market === "UPBIT" && s.key === "market_cap")
  );

  const { data, error, isLoading } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=30`,
    fetcher,
    {
      refreshInterval: (latest) =>
        !latest || latest.length === 0 ? 4000 : 5000,
      keepPreviousData: true,
    }
  );

  if (error?.message?.includes("401")) {
    router.replace("/login");
    return null;
  }

  const rows = data || [];

  return (
    <div className="-mx-4 -my-6 min-h-screen bg-[#0f1115] px-4 py-6 text-gray-200">
      <div className="mx-auto max-w-5xl">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-xl font-bold text-white">실시간 차트</h1>
          <Link href="/" className="text-sm text-gray-400 hover:text-white">
            기존 대시보드 →
          </Link>
        </div>

        <IndicatorBar />

        {/* 시장 탭 */}
        <div className="mb-3 flex gap-2">
          {MARKETS.map((m) => (
            <button
              key={m.key}
              onClick={() => {
                setMarket(m.key);
                if (m.key === "UPBIT" && sort === "market_cap") setSort("value");
              }}
              className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${
                market === m.key
                  ? "bg-white text-[#0f1115]"
                  : "bg-[#1b1e24] text-gray-400 hover:text-white"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {/* 정렬 칩 */}
        <div className="mb-4 flex flex-wrap gap-2">
          {sortsForMarket.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                sort === s.key
                  ? "bg-[#2b2f36] text-white"
                  : "bg-[#16181d] text-gray-500 hover:text-gray-300"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* 랭킹 테이블 */}
        <div className="overflow-hidden rounded-2xl border border-[#23262d] bg-[#16181d]">
          <div className="grid grid-cols-[36px_1fr_110px_90px_100px] items-center gap-2 border-b border-[#23262d] px-4 py-3 text-xs text-gray-500 sm:grid-cols-[36px_1fr_120px_90px_110px_110px]">
            <div>순위</div>
            <div>종목</div>
            <div className="text-right">현재가</div>
            <div className="text-right">등락률</div>
            <div className="hidden text-right sm:block">거래대금</div>
            <div className="text-right">시가총액</div>
          </div>

          {isLoading && rows.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-500">
              불러오는 중…
            </div>
          )}
          {!isLoading && rows.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-gray-500">
              데이터가 없습니다. (Toss 허용 IP 등록을 확인해 주세요)
            </div>
          )}

          {rows.map((row, i) => {
            const p = pctText(row.change_pct);
            return (
              <Link
                key={`${row.market}-${row.code}`}
                href={`/symbols/${row.market}/${encodeURIComponent(row.code)}`}
                className="grid grid-cols-[36px_1fr_110px_90px_100px] items-center gap-2 border-b border-[#1b1e24] px-4 py-3 text-sm transition last:border-0 hover:bg-[#1b1e24] sm:grid-cols-[36px_1fr_120px_90px_110px_110px]"
              >
                <div className="text-gray-500">{i + 1}</div>
                <div className="flex min-w-0 items-center gap-2.5">
                  <Logo row={row} />
                  <div className="min-w-0">
                    <div className="truncate font-medium text-white">
                      {row.name}
                    </div>
                    <div className="text-[11px] text-gray-500">{row.code}</div>
                  </div>
                </div>
                <div className="text-right font-medium text-white">
                  {fmtPriceCell(row)}
                </div>
                <div className={`text-right font-medium ${p.c}`}>{p.t}</div>
                <div className="hidden text-right text-gray-400 sm:block">
                  {fmtCompact(row.value)}
                </div>
                <div className="text-right text-gray-400">
                  {fmtCompact(row.market_cap)}
                </div>
              </Link>
            );
          })}
        </div>

        <p className="mt-4 text-center text-xs text-gray-600">
          시세·랭킹·로고 제공: 토스증권 · 5초마다 자동 갱신
        </p>
      </div>
    </div>
  );
}
