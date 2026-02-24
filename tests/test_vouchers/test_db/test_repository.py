from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.utils import get_now
from app.vouchers.db.models import Base
from app.vouchers.db.repository import AsyncVoucherRepository
from app.vouchers.model import Voucher, VoucherPatch, VoucherStatus


@pytest.fixture()
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def repo(db_engine):
    return AsyncVoucherRepository(db_engine)


def make_voucher(code: str, discount: int = 10) -> Voucher:
    return Voucher(
        code=code,
        discount_percentage=discount,
        valid_until=get_now() + timedelta(days=30),
        status=VoucherStatus.ACTIVE,
    )


def make_patch(
    code: str,
    discount: int | None = None,
    days_valid: int | None = None,
    status: VoucherStatus | None = None,
    now=None,
) -> VoucherPatch:
    valid_until = None
    if days_valid is not None:
        base_now = now if now is not None else get_now()
        valid_until = base_now + timedelta(days=days_valid)
    return VoucherPatch(
        code=code,
        discount_percentage=discount,
        valid_until=valid_until,
        status=status,
    )


class TestAsyncVoucherRepository:
    async def test_add_and_get_by_code(self, repo):
        voucher = make_voucher("code-1")

        await repo.add(voucher)
        loaded = await repo.get_by_code("code-1")

        assert loaded is not None
        assert loaded.code == voucher.code
        assert loaded.discount_percentage == voucher.discount_percentage

    async def test_add_many_and_get_many_by_codes_ordered_by_creation_date(self, repo):
        vouchers = [
            make_voucher("code-1"),
            make_voucher("code-2"),
            make_voucher("code-3"),
        ]

        await repo.add_many(vouchers)
        loaded = await repo.get_many(codes=["code-3", "code-1"])

        assert [voucher.code for voucher in loaded] == ["code-1", "code-3"]

    async def test_get_many_with_pagination(self, repo):
        vouchers = [make_voucher(f"code-{idx}") for idx in range(5)]

        await repo.add_many(vouchers)
        loaded = await repo.get_many(limit=2, offset=1)

        assert len(loaded) == 2
        assert loaded[0].code == "code-1"
        assert loaded[1].code == "code-2"

    async def test_add_overwrites_existing_by_code(self, repo):
        original = make_voucher("code-1", discount=10)
        updated = make_voucher("code-1", discount=25)

        await repo.add(original)
        await repo.add(updated)
        loaded = await repo.get_by_code("code-1")

        assert loaded is not None
        assert loaded.discount_percentage == 25

    async def test_delete_many_removes_and_raises_on_missing(self, repo):
        vouchers = [make_voucher("code-1"), make_voucher("code-2")]

        await repo.add_many(vouchers)
        await repo.delete_many(["code-1"])
        remaining = await repo.get_many()

        assert [voucher.code for voucher in remaining] == ["code-2"]

        try:
            await repo.delete_many(["missing"])
            assert False, "Expected ValueError for missing voucher code"
        except ValueError as exc:
            assert "missing" in str(exc)

    async def test_update_many_updates_fields_and_returns_in_patch_order(self, repo):
        base_now = get_now()
        voucher_1 = make_voucher("code-1", discount=10)
        voucher_2 = make_voucher("code-2", discount=15)
        original_created_1 = voucher_1.created_at
        original_created_2 = voucher_2.created_at

        await repo.add_many([voucher_1, voucher_2])

        patches = [
            make_patch("code-2", discount=25, status=VoucherStatus.INACTIVE),
            make_patch("code-1", days_valid=45, now=base_now),
        ]
        updated = await repo.update_many(patches)

        assert [voucher.code for voucher in updated] == ["code-2", "code-1"]
        updated_by_code = {voucher.code: voucher for voucher in updated}
        assert updated_by_code["code-2"].discount_percentage == 25
        assert updated_by_code["code-2"].status == VoucherStatus.INACTIVE
        assert (
            updated_by_code["code-1"].valid_until.date() == (base_now + timedelta(days=45)).date()
        )
        assert updated_by_code["code-1"].created_at == original_created_1
        assert updated_by_code["code-2"].created_at == original_created_2
        assert updated_by_code["code-1"].updated_at is not None
        assert updated_by_code["code-2"].updated_at is not None

        stored = await repo.get_many(codes=["code-1", "code-2"])
        stored_by_code = {voucher.code: voucher for voucher in stored}
        assert stored_by_code["code-2"].discount_percentage == 25
        assert stored_by_code["code-2"].status == VoucherStatus.INACTIVE
        assert stored_by_code["code-1"].valid_until.date() == (base_now + timedelta(days=45)).date()
        assert stored_by_code["code-1"].updated_at is not None
        assert stored_by_code["code-2"].updated_at is not None

    async def test_update_many_missing_code_raises_and_no_partial_update(self, repo):
        voucher = make_voucher("code-1", discount=10)
        await repo.add(voucher)

        patches = [
            make_patch("code-1", discount=30),
            make_patch("missing", discount=40),
        ]

        try:
            await repo.update_many(patches)
            assert False, "Expected ValueError for missing voucher code"
        except ValueError as exc:
            assert "missing" in str(exc)

        loaded = await repo.get_by_code("code-1")
        assert loaded is not None
        assert loaded.discount_percentage == 10
        assert loaded.updated_at is None

    async def test_update_many_empty_list_is_noop(self, repo):
        voucher = make_voucher("code-1", discount=10)
        await repo.add(voucher)

        updated = await repo.update_many([])
        assert updated == []

        loaded = await repo.get_by_code("code-1")
        assert loaded is not None
        assert loaded.discount_percentage == 10
        assert loaded.updated_at is None

    async def test_update_many_with_only_code_sets_updated_at(self, repo):
        voucher = make_voucher("code-1", discount=10)
        await repo.add(voucher)

        patches = [make_patch("code-1")]
        updated = await repo.update_many(patches)

        assert len(updated) == 1
        assert updated[0].discount_percentage == 10
        assert updated[0].updated_at is not None

        loaded = await repo.get_by_code("code-1")
        assert loaded is not None
        assert loaded.updated_at is not None
