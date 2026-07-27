export function Footer() {
  return (
    <footer className="mt-8 border-t border-bg-3 px-6 py-6 text-[11px] leading-relaxed text-ink-4">
      <div className="mx-auto max-w-5xl space-y-1.5">
        <p>
          <span className="font-semibold text-ink-3">papertrade</span>는 실제 돈이
          오가지 않는 개인용 <span className="text-ink-3">모의투자(페이퍼 트레이딩)</span>{" "}
          서비스입니다. 실제 매매·계좌·자금·수익과는 무관합니다.
        </p>
        <p>
          시세·종목·차트·환율 정보는 토스증권 Open API, 업비트(Upbit) 등 외부
          데이터를 사용하며, 지연·오차·오류가 있을 수 있습니다. 표시되는 모든
          수치는 참고용이며 정확성을 보장하지 않습니다.
        </p>
        <p>
          본 서비스의 어떤 내용도 투자 권유·자문이 아니며, 실제 투자 판단 및 그
          결과에 대한 책임은 이용자 본인에게 있습니다. 각 데이터의 권리는 해당
          제공처(토스증권, 업비트 등)에 있습니다.
        </p>
        <p className="pt-1 text-ink-4">
          © 2026 papertrade · 개인 학습·비영리 목적으로 제작되었습니다.
        </p>
      </div>
    </footer>
  );
}
