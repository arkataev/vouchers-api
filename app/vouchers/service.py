from datetime import datetime

from app.vouchers.model import Voucher, VoucherStatus


def create_voucher(
    valid_until: datetime, discount_percentage: int, status: VoucherStatus
) -> Voucher:
    voucher = Voucher(
        discount_percentage=discount_percentage,
        valid_until=valid_until,
        status=status,
    )
    return voucher
