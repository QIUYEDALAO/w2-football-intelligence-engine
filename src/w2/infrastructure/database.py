from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase

from w2.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def _prepare_sqlite_path(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    database_path = make_url(url).database
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def create_engine(settings: Settings | None = None) -> Engine:
    resolved = settings or get_settings()
    url = resolved.database_url.get_secret_value()
    _prepare_sqlite_path(url)
    if not url.startswith("sqlite"):
        return _shared_engine(os.getpid(), url)
    return sqlalchemy_create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=8)
def _shared_engine(process_id: int, url: str) -> Engine:
    del process_id
    return sqlalchemy_create_engine(url, pool_pre_ping=True)


def database_status(settings: Settings | None = None) -> str:
    try:
        engine = create_engine(settings)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        return "ok"
    except Exception:
        return "unavailable"
