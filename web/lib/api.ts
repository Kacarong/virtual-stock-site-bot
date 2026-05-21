// API helpers. Next.js rewrites /api/* → backend.

export async function api<T = any>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const r = await fetch(`/api${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!r.ok) {
    let msg = `API ${r.status}`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export function fmtKRW(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  return Math.round(n).toLocaleString() + " 원";
}

export function fmtUSD(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 }) + " 달러";
}

export function fmtNum(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

/** 코인용 가격대별 소수점 자동 조정 (BTC 100M원 ~ SHIB 0.04원 모두 자연스럽게). */
export function fmtSmart(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  const abs = Math.abs(n);
  let digits: number;
  if (abs >= 1000) digits = 0;
  else if (abs >= 100) digits = 1;
  else if (abs >= 1) digits = 2;
  else if (abs >= 0.01) digits = 4;
  else if (abs >= 0.0001) digits = 6;
  else digits = 8;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

/** 시장/통화에 맞춰 가격 + 단위 표기.
 *  - KRX (주식, KRW): 정수 + "원"
 *  - UPBIT (코인, KRW): 가격대별 소수점 + "원"
 *  - NASDAQ/NYSE (USD): 소수점 2자리 + "달러"
 */
export function fmtPrice(
  v: string | number | null | undefined,
  market?: string,
  currency?: string
): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  const m = (market || "").toUpperCase();
  const cur = (currency || "").toUpperCase();
  if (cur === "USD" || m === "NASDAQ" || m === "NYSE" || m === "AMEX") {
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 }) + " 달러";
  }
  if (m === "UPBIT") {
    return fmtSmart(n) + " 원";
  }
  // KRX 등 KRW 주식 — 정수 원
  return Math.round(n).toLocaleString() + " 원";
}

/** 수량 표기 — 주식/ETF는 정수, 코인은 trailing 0 제거. */
export function fmtQty(qty: string | number | null | undefined, market?: string): string {
  if (qty === null || qty === undefined) return "-";
  const n = Number(qty);
  if (!isFinite(n)) return "-";
  if ((market || "").toUpperCase() === "UPBIT") {
    // 코인: 의미있는 소수점까지만
    const s = n.toFixed(8);
    return s.replace(/\.?0+$/, "") || "0";
  }
  return Math.floor(n).toLocaleString();
}

export function pctClass(pct: string | number): string {
  const n = Number(pct);
  if (n > 0) return "text-up";
  if (n < 0) return "text-down";
  return "text-ink-2";
}
