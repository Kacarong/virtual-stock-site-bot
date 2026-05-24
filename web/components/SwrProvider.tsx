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
        // 페이지 이동 후 돌아왔을 때 이전 데이터 유지 (빈 화면 깜박임 방지)
        keepPreviousData: true,
        // 짧은 시간 내 동일 키 중복 호출 방지
        dedupingInterval: 2000,
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
