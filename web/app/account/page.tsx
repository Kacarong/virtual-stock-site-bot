"use client";

import { useState } from "react";
import { HoldingsView } from "@/components/HoldingsView";
import { OrdersView } from "@/components/OrdersView";

export default function AccountPage() {
  const [tab, setTab] = useState<"holdings" | "orders">("holdings");
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">내 계좌</h1>
      <div className="flex gap-2">
        {(
          [
            ["holdings", "보유종목"],
            ["orders", "주문·거래"],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded-xl px-4 py-2 text-sm font-semibold ${
              tab === k ? "bg-brand text-brand-fg" : "bg-bg-1 text-ink-2"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "holdings" ? <HoldingsView /> : <OrdersView />}
    </div>
  );
}
