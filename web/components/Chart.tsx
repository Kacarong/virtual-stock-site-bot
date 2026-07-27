"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
} from "lightweight-charts";

type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type Props = {
  data: Candle[];
  /** 가격 배수 — USD 캔들을 KRW로 표시할 때 환율 등을 곱함. 기본 1 */
  priceScale?: number;
  /** 가격 단위 표기 ("원" / "달러" 등). 없으면 단위 없이 숫자만 표기 */
  unitLabel?: string;
  /** KRW 모드: 정수 + ","; USD 모드: 소수점 2자리. 기본 auto */
  integerOnly?: boolean;
  /** 실시간 현재가(원 통화 기준, priceScale 적용 전). 마지막 봉을 실시간 갱신. */
  livePrice?: number;
  /** 봉 간격(초). 분/5분/1시간봉이면 시간 넘어갈 때 새 봉 생성. 일봉 등은 미지정. */
  intervalSec?: number;
};

export function Chart({
  data,
  priceScale = 1,
  unitLabel,
  integerOnly,
  livePrice,
  intervalSec,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lastCandleRef = useRef<{
    time: any;
    open: number;
    high: number;
    low: number;
    close: number;
  } | null>(null);
  const [isDark, setIsDark] = useState(false);

  // 다크모드 감지 (<html>.dark 클래스) — 토글 시 차트 색도 갱신
  useEffect(() => {
    const el = document.documentElement;
    const update = () => setIsDark(el.classList.contains("dark"));
    update();
    const obs = new MutationObserver(update);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current) return;
    const bgColor = isDark ? "#16181D" : "#F8F9FB";
    const textColor = isDark ? "#B0B8C1" : "#4E5968";
    const gridColor = isDark ? "#23262D" : "#E6E9EE";
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: bgColor },
        textColor: textColor,
        fontFamily: "Pretendard, ui-sans-serif, system-ui",
      },
      grid: {
        horzLines: { color: gridColor },
        vertLines: { color: gridColor },
      },
      rightPriceScale: {
        borderVisible: false,
        scaleMargins: { top: 0.05, bottom: 0.25 },
      },
      timeScale: { borderVisible: false, timeVisible: true },
      localization: {
        priceFormatter: (p: number) => {
          if (!isFinite(p)) return "-";
          let s: string;
          if (integerOnly) {
            s = Math.round(p).toLocaleString();
          } else {
            const abs = Math.abs(p);
            const digits = abs >= 1000 ? 0 : abs >= 1 ? 2 : 4;
            s = p.toLocaleString(undefined, {
              minimumFractionDigits: 0,
              maximumFractionDigits: digits,
            });
          }
          return unitLabel ? `${s} ${unitLabel}` : s;
        },
      },
    });
    chartRef.current = chart;

    // 유효한 캔들만 (null/NaN/timestamp 누락 방어 + 시간 오름차순 + 중복 제거)
    const isNum = (v: any) => typeof v === "number" && isFinite(v);
    const clean = data
      .filter(
        (d) =>
          isNum(d?.time) &&
          isNum(d?.open) &&
          isNum(d?.high) &&
          isNum(d?.low) &&
          isNum(d?.close)
      )
      .sort((a, b) => a.time - b.time)
      .filter((d, i, arr) => i === 0 || d.time !== arr[i - 1].time);

    // 메인 캔들 (한국식 상승=빨강, 하락=파랑)
    const candle = chart.addCandlestickSeries({
      upColor: "#FF4D4D",
      downColor: "#3182F6",
      wickUpColor: "#FF4D4D",
      wickDownColor: "#3182F6",
      borderVisible: false,
    });
    // lightweight-charts는 시간축을 UTC로 렌더 → 로컬(KST 등) 표시를 위해
    // 각 시간에 로컬 오프셋(초)을 더해 "가짜 UTC = 로컬시간"으로 만든다.
    const tz = -new Date().getTimezoneOffset() * 60;
    const scaled = clean.map((d) => ({
      time: (d.time + tz) as any,
      open: d.open * priceScale,
      high: d.high * priceScale,
      low: d.low * priceScale,
      close: d.close * priceScale,
    }));
    candle.setData(scaled as any);
    candleRef.current = candle;
    lastCandleRef.current = scaled.length ? scaled[scaled.length - 1] : null;

    // 거래량 막대 (오버레이 — 화면 하단 25% 차지)
    const hasVolume = clean.some((d) => isNum(d.volume) && (d.volume as number) > 0);
    if (hasVolume) {
      const volume = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "", // 오버레이
        color: "#3182F6",
      });
      volume.priceScale().applyOptions({
        scaleMargins: { top: 0.78, bottom: 0 },
      });
      volume.setData(
        clean.map((d) => ({
          time: (d.time + tz) as any,
          value: isNum(d.volume) ? (d.volume as number) : 0,
          // 양봉=빨강, 음봉=파랑 (반투명)
          color: d.close >= d.open ? "#FF4D4D88" : "#3182F688",
        })) as any
      );
    }

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
  }, [data, priceScale, unitLabel, integerOnly, isDark]);

  // 실시간 현재가로 봉 갱신 (전체 재생성 없이 update만).
  // 분/5분/1시간봉이면 시간이 다음 봉으로 넘어갈 때 새 봉을 append.
  useEffect(() => {
    if (livePrice == null || !isFinite(livePrice)) return;
    const c = candleRef.current;
    const last = lastCandleRef.current;
    if (!c || !last) return;
    const p = livePrice * priceScale;
    let bucket: number | null = null;
    if (intervalSec && intervalSec < 86400) {
      // 캔들 시간이 로컬 오프셋만큼 shift돼 있으므로 버킷도 동일하게 맞춘다.
      const tz = -new Date().getTimezoneOffset() * 60;
      const nowShifted = Math.floor(Date.now() / 1000) + tz;
      bucket = Math.floor(nowShifted / intervalSec) * intervalSec;
    }
    if (bucket != null && bucket > Number(last.time)) {
      const nc = { time: bucket, open: p, high: p, low: p, close: p } as any;
      try {
        c.update(nc);
        lastCandleRef.current = nc;
      } catch {}
    } else {
      const updated = {
        time: last.time,
        open: last.open,
        high: Math.max(last.high, p),
        low: Math.min(last.low, p),
        close: p,
      };
      try {
        c.update(updated as any);
        lastCandleRef.current = updated;
      } catch {}
    }
  }, [livePrice, priceScale, intervalSec]);

  return <div ref={ref} className="h-[420px] w-full" />;
}
