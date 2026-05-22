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

export function Chart({ data }: { data: Candle[] }) {
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
          const abs = Math.abs(p);
          const digits = abs >= 1000 ? 0 : abs >= 1 ? 2 : 4;
          return p.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: digits,
          });
        },
      },
    });
    chartRef.current = chart;

    // 메인 캔들 (한국식 상승=빨강, 하락=파랑)
    const candle = chart.addCandlestickSeries({
      upColor: "#FF4D4D",
      downColor: "#3182F6",
      wickUpColor: "#FF4D4D",
      wickDownColor: "#3182F6",
      borderVisible: false,
    });
    candle.setData(data as any);

    // 거래량 막대 (오버레이 — 화면 하단 25% 차지)
    const hasVolume = data.some((d) => d.volume && d.volume > 0);
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
        data.map((d) => ({
          time: d.time as any,
          value: d.volume ?? 0,
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
  }, [data]);

  return <div ref={ref} className="h-[420px] w-full" />;
}
