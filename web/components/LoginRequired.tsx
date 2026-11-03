import Link from "next/link";

/** 비로그인 상태 안내 — 로그인이 필요한 화면/동작에서 "불러오는 중" 대신 표시. */
export function LoginRequired({
  message = "로그인이 필요합니다.",
  compact = false,
}: {
  message?: string;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <div className="mt-3 flex items-center justify-between gap-3 rounded bg-brand/10 p-3 text-xs">
        <span className="text-ink-2">{message}</span>
        <Link
          href="/login"
          className="shrink-0 rounded-lg bg-brand px-3 py-1.5 font-semibold text-brand-fg"
        >
          로그인
        </Link>
      </div>
    );
  }
  return (
    <div className="rounded-3xl bg-bg-1 p-10 text-center shadow-sm">
      <p className="text-sm text-ink-2">{message}</p>
      <Link
        href="/login"
        className="mt-4 inline-block rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-brand-fg"
      >
        로그인하러 가기
      </Link>
    </div>
  );
}
