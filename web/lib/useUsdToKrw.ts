"use client";

import { useEffect, useState } from "react";

const KEY = "showKrw";
const EVT = "showKrw:change";

/**
 * 미국주식 화면의 USD/KRW 표시 토글 — 페이지 간 공유.
 * - localStorage에 저장 → 새로고침/다른 페이지에서도 유지
 * - 같은 탭 내 동기화는 커스텀 이벤트 사용
 */
export function useUsdToKrw(): [boolean, (v: boolean) => void] {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(localStorage.getItem(KEY) === "1");
    } catch {}
    const onChange = (e: Event) => {
      const ce = e as CustomEvent<boolean>;
      setShow(ce.detail);
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY) setShow(e.newValue === "1");
    };
    window.addEventListener(EVT, onChange as EventListener);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVT, onChange as EventListener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const update = (v: boolean) => {
    setShow(v);
    try {
      localStorage.setItem(KEY, v ? "1" : "0");
    } catch {}
    window.dispatchEvent(new CustomEvent(EVT, { detail: v }));
  };

  return [show, update];
}
