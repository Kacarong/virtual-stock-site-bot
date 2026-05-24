"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api, fmtPrice, pctClass } from "@/lib/api";
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
};

type Sort = "value" | "volume" | "change" | "decline" | "market_cap";

const SORTS: { key: Sort; label: string }[] = [
  { key: "value", label: "거래대금" },
  { key: "volume", label: "거래량" },
  { key: "market_cap", label: "시가총액" },
  { key: "change", label: "급등" },
  { key: "decline", label: "급락" },
];

const fetcher = (u: string) => api(u);

function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined) return "-";
  const v = Number(n);
  if (!isFinite(v) || v <= 0) return "-";
  const abs = Math.abs(v);
  if (abs >= 1e12) return (v / 1e12).toFixed(1) + "조";
  if (abs >= 1e8) return (v / 1e8).toFixed(1) + "억";
  if (abs >= 1e4) return (v / 1e4).toFixed(1) + "만";
  return Math.round(v).toLocaleString();
}

function PopularPanel({
  market,
  title,
  refreshMs,
}: {
  market: "KRX" | "US" | "UPBIT";
  title: string;
  refreshMs: number;
}) {
  const [sort, setSort] = useState<Sort>("value");
  // 해외주식만 USD/KRW 토글 (페이지 간 공유)
  const [showKrw, setShowKrw] = useUsdToKrw();
  // UPBIT는 시가총액 미지원 → 옵션에서 제외
  const sortsForMarket = SORTS.filter(
    (s) => !(market === "UPBIT" && s.key === "market_cap")
  );

  const { data, error } = useSWR<Row[]>(
    `/market/popular?market=${market}&sort=${sort}&limit=10`,
    fetcher,
    {
      // 데이터가 비었으면 (콜드 스타트 케이스) 빠르게 재시도
      refreshInterval: (latest) =>
        !latest || latest.length === 0 ? 4000 : refreshMs,
      keepPreviousData: true,
    }
  );

  // 백엔드가 일시적으로 빈 배열을 반환해도 마지막 성공 데이터를 화면에 유지
  // (sort 변경 시에는 ref 리셋 — 새 정렬 데이터를 받기 전까지 잠깐 stale 표기)
  const lastGoodRef = useRef<Row[] | null>(null);
  useEffect(() => {
    if (data && data.length > 0) lastGoodRef.current = data;
  }, [data]);
  useEffect(() => {
    lastGoodRef.current = null;
  }, [sort]);
  const displayData =
    data && data.length > 0 ? data : lastGoodRef.current ?? data;

  // 환율 (US 패널만)
  const { data: fx } = useSWR<{ usdkrw: string }>(
    market === "US" ? "/portfolio" : null,
    fetcher,
    { refreshInterval: 60000 }
  );
  const rate = fx?.usdkrw ? Number(fx.usdkrw) : null;

  return (
    <div className="flex flex-col rounded-3xl bg-white shadow-sm">
      <div className="border-b border-bg-3 px-5 py-3">
        <h3 className="font-semibold whitespace-nowrap">{title}</h3>
        <div className="mt-2 flex flex-wrap gap-1">
          {sortsForMarket.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`rounded-full px-2 py-1 text-[11px] whitespace-nowrap ${
                sort === s.key
                  ? "bg-ink-1 text-white"
                  : "bg-bg-2 text-ink-3 hover:bg-bg-3"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {market === "US" && (
        <div className="flex justify-end gap-1 border-b border-bg-3 px-5 py-2">
          <button
            onClick={() => setShowKrw(false)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] ${
              !showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            달러로 보기
          </button>
          <button
            onClick={() => setShowKrw(true)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] ${
              showKrw ? "bg-ink-1 text-white" : "bg-bg-2 text-ink-3"
            }`}
          >
            원화로 보기
          </button>
        </div>
      )}

      <div className="flex-1">
        {/* 일시적 에러/빈 응답이여도 이전 데이터가 있으면 그대로 보여줌 (깜빡임 방지) */}
        {error && !displayData?.length ? (
          <div className="p-6 text-center text-xs text-red-500">불러오기 실패</div>
        ) : !displayData?.length ? (
          // 콜드 부팅 첫 fetch — 부정확한 폴백을 보여주지 않고 로딩 상태 유지
          // (SWR 4초 polling이 백그라운드에서 fetch 완료를 받아옴)
          <div className="flex flex-col items-center gap-2 p-6 text-center text-xs text-ink-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-bg-3 border-t-ink-2" />
            <span>데이터 불러오는 중…</span>
          </div>
        ) : (
          <ul className="divide-y divide-bg-3">
            {displayData.map((r, i) => {
              const priceNum =
                r.price === null || r.price === undefined
                  ? null
                  : Number(r.price);
              const validPrice =
                priceNum !== null && isFinite(priceNum) && priceNum > 0;
              const chgNum =
                r.change_pct === null || r.change_pct === undefined
                  ? null
                  : Number(r.change_pct);
              const validChg = chgNum !== null && isFinite(chgNum);
              const volNum = r.volume ?? 0;
              const valNum = r.value ?? 0;
              // US + 원화 표시 모드 — 환율 곱해서 KRX처럼 표시
              const displayPrice =
                validPrice && market === "US" && showKrw && rate
                  ? (priceNum as number) * rate
                  : priceNum;
              const displayMarket =
                market === "US" && showKrw && rate ? "KRX" : r.market;
              return (
                <li key={`${r.market}-${r.code}`}>
                  <Link
                    href={`/symbols/${r.market}/${encodeURIComponent(r.code)}`}
                    className="flex items-center gap-3 px-5 py-2.5 hover:bg-bg-2"
                  >
                    <span className="w-5 text-right text-xs text-ink-3">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold">
                        {r.name}
                      </div>
                      <div className="text-[11px] text-ink-3">
                        {sort === "volume"
                          ? fmtCompact(volNum)
                          : sort === "market_cap"
                          ? fmtCompact(r.market_cap)
                          : fmtCompact(valNum)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-semibold">
                        {validPrice
                          ? fmtPrice(displayPrice as number, displayMarket)
                          : "-"}
                      </div>
                      <div
                        className={`text-[11px] ${
                          validChg ? pctClass(chgNum as number) : "text-ink-3"
                        }`}
                      >
                        {validChg
                          ? `${(chgNum as number) >= 0 ? "+" : ""}${(chgNum as number).toFixed(2)}%`
                          : "-"}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-bg-3 px-5 py-2 text-center">
        <Link
          href={`/popular/${market}`}
          className="text-[11px] text-ink-3 hover:text-ink-1"
        >
          전체보기 →
        </Link>
      </div>
    </div>
  );
}

export function PopularBoard() {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <PopularPanel market="KRX" title="국내주식" refreshMs={30000} />
      <PopularPanel market="US" title="해외주식" refreshMs={30000} />
      <PopularPanel market="UPBIT" title="코인" refreshMs={5000} />
    </div>
  );
}
