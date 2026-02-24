from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine

from app.vouchers.db.models import Base

DATABASE_URL = "sqlite+aiosqlite:///./vouchers.db"

engine = create_async_engine(DATABASE_URL, future=True)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    await engine.dispose()
