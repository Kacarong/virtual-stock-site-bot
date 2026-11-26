"""SQLAlchemy 엔진/세션."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite 파일 디렉터리가 없으면 생성."""
    if url.startswith("sqlite:///"):
        path = Path(url.replace("sqlite:///", "/", 1))
        path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.DATABASE_URL)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utc_iso(dt: datetime | None) -> str | None:
    """DB의 naive 시각(UTC)을 오프셋 포함 ISO로. 오프셋이 없으면 브라우저가 현지시각으로 읽어 9시간 어긋난다."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def lock_for_update(db: Session, user_id: int) -> None:
    """잔고를 읽기 전에 SQLite 쓰기 잠금을 잡는다.

    SQLite는 트랜잭션의 첫 쓰기부터 commit/rollback까지 DB 전체 쓰기를 독점한다.
    잠근 뒤 다시 읽은 잔고·주문 상태는 그동안 다른 프로세스(API·체결기)가 바꿀 수 없다.
    잠근 동안에는 await(네트워크 호출)를 하지 말 것 — 다른 쓰기가 모두 대기한다.
    """
    db.execute(text("UPDATE users SET id = id WHERE id = :id"), {"id": user_id})
    db.expire_all()


def init_db() -> None:
    """모든 모델을 import 한 뒤 테이블 생성."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """create_all은 기존 테이블에 컬럼을 추가하지 않으므로 필요한 컬럼만 직접 추가."""
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(orders)")}
        if "reserve_price" not in cols:
            try:
                c.exec_driver_sql("ALTER TABLE orders ADD COLUMN reserve_price NUMERIC(20, 8)")
            except Exception as e:  # API·Worker가 동시에 기동하며 먼저 추가한 경우
                if "duplicate column" not in str(e):
                    raise
