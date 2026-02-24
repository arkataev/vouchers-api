from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.vouchers.model import VoucherStatus


class Base(DeclarativeBase):
    pass


class VoucherORM(Base):
    __tablename__ = "vouchers"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    discount_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[VoucherStatus] = mapped_column(Enum(VoucherStatus))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
