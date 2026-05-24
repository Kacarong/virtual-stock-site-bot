"""인증 라우터: Discord OAuth + 관리자 ID/PW + DEV 로그인."""
from __future__ import annotations

import hmac
import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    current_user,
    get_or_create_user,
    make_session_token,
)
from ..config import settings
from ..db import get_db
from ..models import User

# 관리자 계정용 가상 discord_id (Discord 19자리 숫자와 충돌 안 함)
ADMIN_DISCORD_ID = "admin:local"

router = APIRouter(prefix="/auth", tags=["auth"])

DISCORD_API = "https://discord.com/api"
DISCORD_AUTH = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN = f"{DISCORD_API}/oauth2/token"
DISCORD_ME = f"{DISCORD_API}/users/@me"


def _set_session(resp: Response, user_id: int) -> None:
    token = make_session_token(user_id)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # NAS 외부노출 시 HTTPS면 True로
    )


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {
        "id": user.id,
        "discord_id": user.discord_id,
        "username": user.username,
        "avatar_url": user.avatar_url,
        "cash_krw": str(user.cash_krw),
        "cash_usd": str(user.cash_usd),
        "is_admin": user.is_admin,
    }


@router.post("/logout")
def logout(resp: Response) -> dict:
    resp.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


# --- 관리자 ID/PW 로그인 -------------------------------------------

class AdminLoginBody(BaseModel):
    username: str
    password: str


@router.post("/admin-login")
def admin_login(
    body: AdminLoginBody,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """단일 관리자 계정 로그인 (Discord 불필요).

    config의 ADMIN_USERNAME/ADMIN_PASSWORD와 일치 시 세션 발급.
    """
    # 타이밍 공격 방지용 상수시간 비교
    ok_user = hmac.compare_digest(body.username, settings.ADMIN_USERNAME)
    ok_pw = hmac.compare_digest(body.password, settings.ADMIN_PASSWORD)
    if not (ok_user and ok_pw):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    user = db.query(User).filter(User.discord_id == ADMIN_DISCORD_ID).first()
    if not user:
        user = get_or_create_user(
            db,
            discord_id=ADMIN_DISCORD_ID,
            username=settings.ADMIN_USERNAME,
            avatar_url=None,
        )
    if not user.is_admin:
        user.is_admin = True
        db.commit()
    _set_session(response, user.id)
    return {
        "ok": True,
        "user_id": user.id,
        "username": user.username,
        "is_admin": True,
    }


# --- DEV 로그인 (DEV_LOGIN=true 일 때만) ----------------------------

@router.post("/dev-login")
def dev_login(
    discord_id: str = "999999999999999999",
    username: str = "dev-user",
    response: Response = None,
    db: Session = Depends(get_db),
) -> dict:
    if not settings.DEV_LOGIN:
        raise HTTPException(status_code=404, detail="dev login disabled")
    user = get_or_create_user(db, discord_id=discord_id, username=username)
    # DEV 로그인 사용자는 자동 admin (로컬/내부망 개발용)
    if not user.is_admin:
        user.is_admin = True
        db.commit()
    _set_session(response, user.id)
    return {
        "ok": True,
        "user_id": user.id,
        "discord_id": user.discord_id,
        "cash_krw": str(user.cash_krw),
    }


# --- Discord OAuth (Stage 5에서 실제 사용) --------------------------

@router.get("/discord/login")
def discord_login(request: Request) -> RedirectResponse:
    if not settings.DISCORD_CLIENT_ID:
        raise HTTPException(status_code=503, detail="discord oauth not configured")
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": settings.DISCORD_CLIENT_ID,
        "redirect_uri": settings.DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "none",
    }
    resp = RedirectResponse(f"{DISCORD_AUTH}?{urllib.parse.urlencode(params)}")
    resp.set_cookie("pt_oauth_state", state, max_age=300, httponly=True, samesite="lax")
    return resp


@router.get("/discord/callback")
async def discord_callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    cookie_state = request.cookies.get("pt_oauth_state")
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=400, detail="state mismatch")

    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            DISCORD_TOKEN,
            data={
                "client_id": settings.DISCORD_CLIENT_ID,
                "client_secret": settings.DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="discord token exchange failed")
        access_token = token_resp.json()["access_token"]

        me_resp = await client.get(
            DISCORD_ME, headers={"Authorization": f"Bearer {access_token}"}
        )
        if me_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="discord profile fetch failed")
        profile = me_resp.json()

    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{profile['id']}/{profile['avatar']}.png"
        if profile.get("avatar")
        else None
    )
    user = get_or_create_user(
        db,
        discord_id=profile["id"],
        username=profile.get("global_name") or profile.get("username", "user"),
        avatar_url=avatar_url,
    )

    # 세션 쿠키 세팅 후 웹으로 리다이렉트
    redirect = RedirectResponse("/")
    redirect.delete_cookie("pt_oauth_state")
    _set_session(redirect, user.id)
    return redirect
