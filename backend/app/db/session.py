from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.modules.audit.immutability import install_audit_immutability


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_engine(settings)


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout_seconds,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session, session.begin():
        yield session


async def database_is_ready() -> bool:
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def dispose_engine() -> None:
    await get_engine().dispose()


from app.modules.realtime.capture import install_realtime_capture  # noqa: E402

install_realtime_capture()
install_audit_immutability()
