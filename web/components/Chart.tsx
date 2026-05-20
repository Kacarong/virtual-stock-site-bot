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
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: "#FF4D4D",
      downColor: "#3182F6",
      wickUpColor: "#FF4D4D",
      wickDownColor: "#3182F6",
      borderVisible: false,
    });
    series.setData(data as any);
    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return <div ref={ref} className="h-[360px] w-full" />;
}
