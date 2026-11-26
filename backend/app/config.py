"""환경 변수 로딩."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 공통
    SECRET_KEY: str = ""  # 필수: openssl rand -hex 32 (비어 있거나 짧으면 기동 거부)
    DEV_LOGIN: bool = False  # 운영에선 꺼둠 (관리자 로그인으로 대체)
    INITIAL_CASH_KRW: int = 50_000_000
    ADMIN_DISCORD_IDS: str = ""  # comma-separated

    # 관리자 ID/PW 로그인 (Discord 없이 들어올 수 있는 단일 admin 계정)
    ADMIN_USERNAME: str = "kacarong12"
    ADMIN_PASSWORD: str = ""  # 비어 있으면 관리자 ID/PW 로그인 비활성

    # DB
    DATABASE_URL: str = "sqlite:////data/papertrade.db"

    # Discord OAuth (Stage 5)
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    # 콜백은 프론트(3000) 프록시를 경유해야 세션 쿠키가 웹앱 도메인에 붙는다.
    DISCORD_REDIRECT_URI: str = "http://localhost:3000/api/auth/discord/callback"
    DISCORD_BOT_TOKEN: str = ""

    # KIS (Stage 2)
    KIS_ENV: str = "vts"
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_ACCOUNT_NO: str = ""

    # Toss 증권 Open API (국내+미국 시세 주 공급자)
    TOSS_API_BASE: str = "https://openapi.tossinvest.com"
    TOSS_CLIENT_ID: str = ""
    TOSS_CLIENT_SECRET: str = ""

    @property
    def admin_discord_ids(self) -> set[str]:
        return {x.strip() for x in self.ADMIN_DISCORD_IDS.split(",") if x.strip()}


settings = Settings()

# 빈/기본 키면 누구나 세션 쿠키(관리자 포함)를 위조할 수 있으므로 기동을 거부한다.
if len(settings.SECRET_KEY) < 32 or settings.SECRET_KEY.startswith("change-me"):
    raise RuntimeError("SECRET_KEY가 비어 있거나 너무 짧습니다 (.env에 openssl rand -hex 32 값 필요)")
