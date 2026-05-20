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
  return "₩ " + Math.round(n).toLocaleString();
}

export function fmtUSD(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  return "$ " + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function fmtNum(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "-";
  const n = Number(v);
  if (!isFinite(n)) return "-";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function pctClass(pct: string | number): string {
  const n = Number(pct);
  if (n > 0) return "text-up";
  if (n < 0) return "text-down";
  return "text-ink-2";
}
