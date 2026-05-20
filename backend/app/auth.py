"""인증.

Stage 1: Discord OAuth 스캐폴드 + DEV_LOGIN 바이패스.
Stage 5에서 Discord OAuth 실제 활성화.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import CashLedger, User

SESSION_COOKIE = "pt_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SECRET_KEY, salt="pt-session-v1")


def make_session_token(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
        return int(data["uid"])
    except (BadSignature, KeyError, ValueError):
        return None


def get_or_create_user(
    db: Session,
    *,
    discord_id: str,
    username: str,
    avatar_url: str | None = None,
) -> User:
    """Discord ID 기반 upsert. 신규면 초기 자본금 지급."""
    user = db.query(User).filter(User.discord_id == discord_id).first()
    if user:
        # 프로필 갱신
        if user.username != username or user.avatar_url != avatar_url:
            user.username = username
            user.avatar_url = avatar_url
        # 관리자 동기화
        user.is_admin = discord_id in settings.admin_discord_ids
        db.commit()
        return user

    # 신규 가입
    is_admin = discord_id in settings.admin_discord_ids
    initial_cash = Decimal(settings.INITIAL_CASH_KRW)
    user = User(
        discord_id=discord_id,
        username=username,
        avatar_url=avatar_url,
        cash_krw=initial_cash,
        cash_usd=Decimal("0"),
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()  # user.id 확보

    db.add(
        CashLedger(
            user_id=user.id,
            currency="KRW",
            amount=initial_cash,
            reason="INITIAL",
            memo="신규가입 초기 자본금",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """세션 쿠키에서 사용자 추출. 없으면 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    uid = read_session_token(token)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user gone")
    return user


def admin_required(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin only")
    return user
