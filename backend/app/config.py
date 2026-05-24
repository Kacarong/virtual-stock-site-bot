"""환경 변수 로딩."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 공통
    SECRET_KEY: str = "change-me"
    DEV_LOGIN: bool = False  # 운영에선 꺼둠 (관리자 로그인으로 대체)
    INITIAL_CASH_KRW: int = 50_000_000
    ADMIN_DISCORD_IDS: str = ""  # comma-separated

    # 관리자 ID/PW 로그인 (Discord 없이 들어올 수 있는 단일 admin 계정)
    ADMIN_USERNAME: str = "kacarong12"
    ADMIN_PASSWORD: str = "96574258AAaa@"

    # DB
    DATABASE_URL: str = "sqlite:////data/papertrade.db"

    # Discord OAuth (Stage 5)
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""
    DISCORD_REDIRECT_URI: str = "http://localhost:8000/auth/discord/callback"
    DISCORD_BOT_TOKEN: str = ""

    # KIS (Stage 2)
    KIS_ENV: str = "vts"
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_ACCOUNT_NO: str = ""

    @property
    def admin_discord_ids(self) -> set[str]:
        return {x.strip() for x in self.ADMIN_DISCORD_IDS.split(",") if x.strip()}


settings = Settings()
