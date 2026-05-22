"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
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
};

export function Chart({ data, priceScale = 1, unitLabel, integerOnly }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#FFFFFF" },
        textColor: "#4E5968",
        fontFamily: "Pretendard, ui-sans-serif, system-ui",
      },
      grid: {
        horzLines: { color: "#F2F4F6" },
        vertLines: { color: "#F2F4F6" },
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
    candle.setData(
      clean.map((d) => ({
        time: d.time as any,
        open: d.open * priceScale,
        high: d.high * priceScale,
        low: d.low * priceScale,
        close: d.close * priceScale,
      })) as any
    );

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
          time: d.time as any,
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
    };
  }, [data, priceScale, unitLabel, integerOnly]);

  return <div ref={ref} className="h-[420px] w-full" />;
}
