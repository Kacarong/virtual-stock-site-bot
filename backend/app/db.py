"""SQLAlchemy 엔진/세션."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
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


def init_db() -> None:
    """모든 모델을 import 한 뒤 테이블 생성."""
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
