from app.vouchers.api.http.v1.schemas import VoucherUpdateRequest


def has_no_duplicates(items: list[str]) -> list[str]:
    """Check if a list has no duplicate elements"""
    if len(items) != len(set(items)):
        raise ValueError("List contains duplicate elements")
    return items


def is_not_empty(items: list[str]) -> list[str]:
    if not items:
        raise ValueError("Value cannot be empty")
    return items


def non_empty_voucher_values_update_request(
    requests: list[VoucherUpdateRequest],
) -> list[VoucherUpdateRequest]:
    for request in requests:
        if not request.code:
            raise ValueError("Voucher code is required")

        if all(
            [
                request.discount_percentage is None,
                request.valid_until is None,
                request.status is None,
            ]
        ):
            raise ValueError(
                f"At least one updated field must be provided for voucher code {request.code} "
            )

    return requests


def has_unique_voucher_codes(
    requests: list[VoucherUpdateRequest],
) -> list[VoucherUpdateRequest]:
    """Ensure that all voucher codes in the request are unique"""
    codes = has_no_duplicates([request.code for request in requests])
    is_not_empty(codes)
    return requests
