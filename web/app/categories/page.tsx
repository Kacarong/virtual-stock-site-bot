"use client";

import { IndustryBoard } from "@/components/IndustryBoard";

export default function CategoriesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">종류별 종목</h1>
        <p className="mt-1 text-xs text-ink-3">
          업종/테마별로 묶어 본 인기 종목 — 한국·미국·코인 모두 한자리에
        </p>
      </div>
      <IndustryBoard />
    </div>
  );
}
