"use client";

import { LiveDashboard } from "@/components/LiveDashboard";
import { MarketStatusBar } from "@/components/MarketStatusBar";
import { SearchBox } from "@/components/SearchBox";

export default function Home() {
  return (
    <div className="space-y-5">
      <MarketStatusBar />
      <SearchBox />
      <LiveDashboard />
    </div>
  );
}
