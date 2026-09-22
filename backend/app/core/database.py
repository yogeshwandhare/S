"""
SQLAlchemy engine, session factory, and declarative base.

The application targets PostgreSQL in production/Docker. For fast local
iteration and the automated test suite, `DATABASE_URL` can point at a
SQLite file instead (see backend/tests/conftest.py) -- the ORM layer avoids
Postgres-only column types so both work, but Alembic migrations and any
JSON/array-heavy queries are only exercised for real against Postgres.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
