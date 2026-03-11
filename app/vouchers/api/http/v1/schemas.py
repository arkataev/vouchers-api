from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.vouchers.model import Voucher, VoucherPatch, VoucherStatus


class VoucherCreateRequest(BaseModel):
    """Request model for creating vouchers."""

    discount_percentage: int = Field(description="Discount percentage (1-100).")
    valid_until: Optional[datetime] = Field(
        description=(
            f"Voucher expiration date. If omitted, defaults to now + {Voucher.MAX_VALIDITY_DAYS} days. "
            f"Naive datetimes are treated as UTC. Must be > now and <= now + {Voucher.MAX_VALIDITY_DAYS} days."
        ),
        default=None,
        exclude_if=lambda v: v is None,
    )
    status: Optional[VoucherStatus] = Field(
        description="Voucher status. Defaults to active if omitted.",
        default=None,
        exclude_if=lambda v: v is None,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "discount_percentage": 15,
                    "valid_until": "2026-12-31T23:59:59Z",
                    "status": "active",
                }
            ]
        }
    }

    def to_model(self) -> Voucher:
        return Voucher(**self.model_dump(exclude_none=True))


class VoucherUpdateRequest(BaseModel):
    """Request model for updating vouchers. At least one field must be provided."""

    code: str = Field(description="Voucher unique code")
    discount_percentage: Optional[int] = Field(
        description="Discount percentage (1-100).",
        default=None,
        exclude_if=lambda v: v is None,
    )
    valid_until: Optional[datetime] = Field(
        description=(
            "Voucher expiration date. Naive datetimes are treated as UTC. "
            f"Must be > now and <= now + {Voucher.MAX_VALIDITY_DAYS} days."
        ),
        default=None,
        exclude_if=lambda v: v is None,
    )
    status: Optional[VoucherStatus] = Field(
        description="Voucher active status",
        default=None,
        exclude_if=lambda v: v is None,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "a1b2c3d4e5f6",
                    "discount_percentage": 20,
                }
            ]
        }
    }

    def to_model(self) -> VoucherPatch:
        return VoucherPatch(**self.model_dump())


class VoucherResponse(BaseModel):
    """Response model for voucher data."""

    code: str = Field(description="Voucher unique code")
    discount_percentage: int = Field(description="Discount percentage")
    valid_until: datetime = Field(description="Voucher expiration date (UTC).")
    status: VoucherStatus = Field(description="Voucher active status")
    created_at: datetime = Field(description="Voucher creation date")
    updated_at: datetime | None = Field(description="Voucher last update date", default=None)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "a1b2c3d4e5f6",
                    "discount_percentage": 15,
                    "valid_until": "2026-12-31T23:59:59Z",
                    "status": "active",
                    "created_at": "2026-02-27T10:00:00Z",
                    "updated_at": None,
                }
            ]
        }
    }

    @classmethod
    def from_model(cls, voucher: Voucher):
        return cls(
            code=voucher.code,
            discount_percentage=voucher.discount_percentage,
            valid_until=voucher.valid_until,
            status=voucher.status,
            created_at=voucher.created_at,
            updated_at=voucher.updated_at,
        )
