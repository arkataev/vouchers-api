from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import engine
from app.utils import get_now, to_utc_time_zone
from app.vouchers.db.models import VoucherORM
from app.vouchers.model import Voucher, VoucherPatch


class AsyncVoucherRepository:
    def __init__(self, engine_):
        self._engine = engine_
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @staticmethod
    def _to_orm(voucher: Voucher) -> VoucherORM:
        return VoucherORM(
            code=voucher.code,
            discount_percentage=voucher.discount_percentage,
            valid_until=voucher.valid_until,
            status=voucher.status,
            created_at=voucher.created_at,
            updated_at=voucher.updated_at,
        )

    @staticmethod
    def _to_model(voucher: VoucherORM) -> Voucher:
        return Voucher(
            code=voucher.code,
            discount_percentage=voucher.discount_percentage,
            valid_until=voucher.valid_until,
            status=voucher.status,
            created_at=to_utc_time_zone(voucher.created_at),
            updated_at=to_utc_time_zone(voucher.updated_at),
        )

    async def add(self, voucher: Voucher) -> None:
        async with self._session_factory() as session:
            await session.merge(self._to_orm(voucher))
            await session.commit()

    async def get_by_code(self, code: str) -> Voucher | None:
        async with self._session_factory() as session:
            result = await session.execute(select(VoucherORM).where(VoucherORM.code == code))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return self._to_model(row)

    async def add_many(self, vouchers: Iterable[Voucher]) -> None:
        async with self._session_factory() as session:
            for voucher in vouchers:
                await session.merge(self._to_orm(voucher))
            await session.commit()

    async def get_many(
        self,
        codes: Iterable[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Voucher]:
        """Returns a list of vouchers sorted by creation date."""
        async with self._session_factory() as session:
            stmt = select(VoucherORM)
            if codes:
                stmt = stmt.where(VoucherORM.code.in_(list(codes)))

            if limit is not None:
                stmt = stmt.offset(offset).limit(limit)

            stmt = stmt.order_by(VoucherORM.created_at.asc())
            result = await session.execute(stmt)
            return [self._to_model(row) for row in result.scalars().all()]

    async def delete_many(self, codes: list[str]) -> None:
        async with self._session_factory() as session:
            if not codes:
                return
            result = await session.execute(
                select(VoucherORM.code).where(VoucherORM.code.in_(codes))
            )
            existing = {row for row, in result.all()}
            missing = [code for code in codes if code not in existing]
            if missing:
                raise ValueError(f"Voucher with code {missing[0]} not found")
            await session.execute(delete(VoucherORM).where(VoucherORM.code.in_(codes)))
            await session.commit()

    async def update_many(self, voucher_patches: Iterable[VoucherPatch]) -> list[Voucher]:
        """Updates multiple vouchers in the database."""
        patches = list(voucher_patches)
        if not patches:
            return []

        async with self._session_factory() as session:
            codes = sorted([patch.code for patch in patches])  # ensures consistent lock ordering

            if len(set(codes)) != len(codes):
                # explicitly check for duplicates
                raise ValueError("Duplicate codes in patch list")

            result = await session.execute(
                select(VoucherORM).where(VoucherORM.code.in_(codes)).with_for_update()
            )
            existing_rows = result.scalars().all()
            existing_by_code = {row.code: row for row in existing_rows}
            missing = [code for code in codes if code not in existing_by_code]

            if missing:
                # prevents partial updates
                raise ValueError(f"Vouchers not found: {', '.join(missing)}")

            now = get_now()
            updated_models: list[Voucher] = []
            for patch in patches:
                row = existing_by_code[patch.code]
                if patch.discount_percentage is not None:
                    row.discount_percentage = patch.discount_percentage
                if patch.valid_until is not None:
                    row.valid_until = patch.valid_until
                if patch.status is not None:
                    row.status = patch.status
                row.updated_at = now
                updated_models.append(self._to_model(row))

            await session.commit()
            return updated_models


async def get_repo() -> AsyncVoucherRepository:
    return AsyncVoucherRepository(engine)
