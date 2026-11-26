// API helpers. Next.js rewrites /api/* → backend.

/** HTTP 상태를 보존하는 에러 — 메시지(detail)만으론 401 여부를 알 수 없어서. */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** 비로그인(401) 에러인지. */
export function isUnauthorized(e: unknown): boolean {
  return (e as any)?.status === 401;
}

// 401을 받은 GET 경로. 비로그인 방문자가 모든 페이지에서 1~5초마다 로그인 필요 API를 계속
// 호출하던 문제 → 같은 경로는 다시 보내지 않고 바로 401로 처리한다.
// 로그인·로그아웃은 전체 페이지 이동(window.location)이라 이 기록도 그때 초기화된다.
const unauthorizedPaths = new Set<string>();

// 탭으로 돌아오면(다른 탭에서 로그인했을 수 있음) 기록을 지워 다시 확인하게 한다.
// capture 단계로 등록해 SWR의 포커스 재검증보다 먼저 지워지게 한다.
if (typeof window !== "undefined") {
  const reset = () => {
    if (document.visibilityState === "visible") unauthorizedPaths.clear();
  };
  window.addEventListener("focus", reset, { capture: true });
  document.addEventListener("visibilitychange", reset, { capture: true });
}

export async function api<T = any>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const isGet = !init?.method || init.method.toUpperCase() === "GET";
  if (isGet && unauthorizedPaths.has(path)) {
    throw new ApiError(401, "not authenticated");
  }
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
    if (r.status === 401 && isGet) unauthorizedPaths.add(path);
    throw new ApiError(r.status, msg);
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
