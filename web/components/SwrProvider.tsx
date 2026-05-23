"use client";

import { SWRConfig } from "swr";

/**
 * 전역 SWR 설정.
 *
 * 백엔드 콜드 스타트(워밍업 ~20초) 동안 첫 요청이 실패하면
 * 기본 설정으로는 5초 간격 무한 재시도하지만 일부 케이스(404 등)는
 * 캐시에 잡혀 다시 안 부른다. 그래서 명시적으로 재시도와
 * 포커스/리커넥트 갱신을 켜둔다.
 */
export function SwrProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: true,
        revalidateOnReconnect: true,
        shouldRetryOnError: true,
        errorRetryInterval: 2000,
        errorRetryCount: 30,
        // 4xx (특히 404) 도 재시도. 401만 즉시 중단(로그인 페이지로 보내야 함).
        onErrorRetry: (error, _key, _cfg, revalidate, { retryCount }) => {
          const msg = (error?.message || "").toString();
          if (msg.includes("401")) return;
          if (retryCount >= 30) return;
          setTimeout(() => revalidate({ retryCount }), 2000);
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
