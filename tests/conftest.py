import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.vouchers.db.models import Base
from app.vouchers.db.repository import AsyncVoucherRepository, get_repo


@pytest.fixture(autouse=True)
async def fresh_repo():
    async def setup():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        repo = AsyncVoucherRepository(engine)
        return repo, engine

    repo, engine = await setup()

    async def _get_repo():
        return repo

    app.dependency_overrides[get_repo] = _get_repo
    yield repo
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
def client():
    return TestClient(app)
