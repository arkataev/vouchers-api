import enum
import secrets
from datetime import datetime, timedelta
from typing import ClassVar, Optional

from pydantic import BaseModel, Field, field_validator

from app.utils import get_now, to_utc_time_zone


def get_voucher_max_validity_date() -> datetime:
    return get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS)


def normalize_and_validate_valid_until(value: datetime) -> datetime:
    utc_time = to_utc_time_zone(value)

    if utc_time is None:
        raise ValueError("valid_until must be provided or omitted entirely")

    now = get_now()
    max_allowed = get_voucher_max_validity_date()

    if utc_time <= now:
        raise ValueError("valid_until must be greater than current date")
    if utc_time > max_allowed:
        raise ValueError(
            f"valid_until must be less than or equal to {Voucher.MAX_VALIDITY_DAYS} days from now"
        )

    return utc_time


class VoucherStatus(enum.StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class VoucherPatch(BaseModel):
    code: str
    discount_percentage: Optional[int] = Field(default=None, ge=1, le=100)
    valid_until: Optional[datetime] = None
    status: Optional[VoucherStatus] = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def validate_expiration_date(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return value
        return normalize_and_validate_valid_until(value)


class Voucher(BaseModel):
    MAX_VALIDITY_DAYS: ClassVar[int] = 365

    code: str = Field(default_factory=lambda: secrets.token_hex(6))
    discount_percentage: int = Field(..., ge=1, le=100)
    valid_until: datetime = Field(default_factory=get_voucher_max_validity_date)
    status: VoucherStatus = Field(default=VoucherStatus.ACTIVE)
    created_at: datetime = Field(default_factory=get_now)
    updated_at: Optional[datetime] = None

    @field_validator("valid_until", mode="before")
    @classmethod
    def validate_expiration_date(cls, value: datetime) -> datetime:
        return normalize_and_validate_valid_until(value)
