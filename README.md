# virtual-stock-site-bot

개인용 가상 주식/코인 모의투자 사이트 + Discord 봇.

실제 시장 시세를 받아와 친구들끼리 가상 잔고로 거래하고, Discord에서 포트폴리오/주문을 조회·실행할 수 있습니다.

## 기능

- 한국 주식·ETF (KIS Open API)
- 미국 주식·ETF (yfinance)
- 코인 (Upbit 공개 API)
- 시장가 / 지정가 / 예약주문
- 수수료·거래세·환전 스프레드 시뮬레이션
- 정규장 / 휴장일 자동 처리
- Discord OAuth 단일 로그인
- 관리자 페이지 + Discord 관리자 명령
- Discord 봇으로 조회·주문

## 스택

- **Backend**: Python 3.12, FastAPI, SQLAlchemy, APScheduler
- **Worker**: 같은 코드베이스, 시세 폴러 + 주문 매처
- **Bot**: discord.py 2.x
- **Frontend**: Next.js 14 (App Router), Tailwind, shadcn/ui, TradingView Lightweight Charts
- **DB**: SQLite (볼륨 마운트)
- **Deploy**: Docker Compose (Synology Container Manager)

## 디렉터리 구조

```
.
├── backend/                 # FastAPI + Worker + Bot (단일 코드베이스)
│   ├── app/
│   │   ├── main.py          # FastAPI 엔트리
│   │   ├── worker.py        # 폴러/매처 엔트리
│   │   ├── bot.py           # Discord 봇 엔트리 (Stage 5)
│   │   ├── config.py        # 환경 변수
│   │   ├── db.py            # SQLAlchemy 세션
│   │   ├── models.py        # DB 모델
│   │   ├── auth.py          # Discord OAuth + Dev 로그인
│   │   ├── routers/         # API 라우터
│   │   └── services/        # 비즈니스 로직
│   ├── pyproject.toml
│   └── Dockerfile
├── web/                     # Next.js
│   ├── app/                 # App Router
│   ├── components/
│   ├── lib/
│   ├── package.json
│   └── Dockerfile
├── data/                    # SQLite, 캐시 (gitignore)
├── docker-compose.yml
├── .env.example
└── README.md
```

## 개발 단계

- **Stage 1 — 기반 (현재)**: Repo 세팅, Docker Compose, SQLite 스키마, Discord OAuth, 사용자 가입 시 5천만원 지급
- **Stage 2 — 시세 파이프라인**: KIS / yfinance / Upbit 폴러, 종목 마스터 동기화, 휴장일 모듈
- **Stage 3 — 거래 엔진**: 시장가/지정가/예약, 수수료·세금, 환율
- **Stage 4 — 웹 UI**: 대시보드, 검색, 차트, 주문, 관리자
- **Stage 5 — Discord 봇**: 조회·주문·관리자 명령

## 실행 (개발)

```bash
cp .env.example .env
# .env 편집 (DEV_LOGIN=true 로 두면 Discord OAuth 없이 테스트 가능)
docker compose up -d
```

- 웹: http://localhost:3000
- API: http://localhost:8000/docs

## 환경 변수

`.env.example` 참고. Stage 1에서 필요한 값:

| 키 | 설명 | 필수 |
|---|---|---|
| `DEV_LOGIN` | true면 Discord OAuth 건너뛰고 임시 사용자로 로그인 | Stage 1 개발용 |
| `INITIAL_CASH_KRW` | 신규 가입자 초기 자본금 (기본 50000000) | - |
| `ADMIN_DISCORD_IDS` | 관리자 Discord ID 콤마구분 | - |
| `SECRET_KEY` | 세션 쿠키 서명용. `openssl rand -hex 32`로 생성 | ✅ |
| `DISCORD_CLIENT_ID` | Discord OAuth | Stage 5에서 |
| `DISCORD_CLIENT_SECRET` | Discord OAuth | Stage 5에서 |
| `DISCORD_REDIRECT_URI` | OAuth 리다이렉트 URL | Stage 5에서 |
| `DISCORD_BOT_TOKEN` | Discord 봇 토큰 | Stage 5에서 |
| `KIS_APP_KEY` | 한국투자증권 앱키 | Stage 2에서 |
| `KIS_APP_SECRET` | 한국투자증권 앱시크릿 | Stage 2에서 |
| `KIS_ACCOUNT_NO` | 한투 계좌번호 (시세조회용) | Stage 2에서 |
| `KIS_ENV` | `vts`(모의) 또는 `real` | Stage 2에서 |

## NAS 배포 (요약, 나중에 자세히)

1. Synology Container Manager 설치
2. SSH로 NAS 접속 → `git clone` → `.env` 작성 → `docker compose up -d`
3. (옵션) Cloudflare Tunnel로 외부 노출

자세한 NAS 배포 가이드는 Stage 5 이후 별도 문서로 제공.
