from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AfterValidator, Field, ValidationError
from typing_extensions import Annotated

from app.vouchers.api.http.v1.schemas import (
    VoucherCreateRequest,
    VoucherResponse,
    VoucherUpdateRequest,
)
from app.vouchers.api.validators import (
    has_no_duplicates,
    has_unique_voucher_codes,
    is_not_empty,
    non_empty_voucher_values_update_request,
)
from app.vouchers.db.repository import AsyncVoucherRepository, get_repo
from app.vouchers.model import Voucher, VoucherStatus

# Avoid overloading resources with too many vouchers processing
VOUCHER_CREATE_LIMIT = 50
VOUCHER_UPDATE_LIMIT = 50
VOUCHER_PAGE_SIZE = 100


UniqueStrList = Annotated[
    list[str],
    AfterValidator(has_no_duplicates),
    AfterValidator(is_not_empty),
]

ValidVoucherUpdateRequest = Annotated[
    list[VoucherUpdateRequest],
    AfterValidator(non_empty_voucher_values_update_request),
    AfterValidator(has_unique_voucher_codes),
]

# TODO:: API layer uses DB directly for simplicity. Normally there would be a service layer between API and DB

router = APIRouter(prefix="/vouchers", tags=["vouchers"])


@router.post(
    "",
    response_model=list[VoucherResponse],
    status_code=status.HTTP_201_CREATED,
    description=(
        "Create multiple vouchers in a single request. "
        "This endpoint is fail-fast: the whole request is rejected if any item is invalid. "
        f"Max items: {VOUCHER_CREATE_LIMIT}."
    ),
)
async def create_vouchers(
    request: Annotated[
        list[VoucherCreateRequest],
        Field(
            max_length=VOUCHER_CREATE_LIMIT,
            json_schema_extra={"minItems": 1},
        ),
    ],
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> list[Voucher]:

    try:
        vouchers = [voucher_request.to_model() for voucher_request in request]
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    await repo.add_many(vouchers)
    return vouchers


@router.post(
    "/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    description=(
        "Delete vouchers by code. "
        "Fail-fast: the whole request is rejected if any code is invalid or not found. "
        f"Max items: {VOUCHER_PAGE_SIZE}."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "One or more provided vouchers not found"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Validation error"},
    },
)
async def delete_vouchers(
    codes: Annotated[
        UniqueStrList,
        Field(
            max_length=VOUCHER_PAGE_SIZE,
            json_schema_extra={"minItems": 1, "uniqueItems": True},
        ),
    ],
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> None:
    try:
        await repo.delete_many(codes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    description=(
        "Deactivate vouchers by code. "
        "Fail-fast: the whole request is rejected if any code is invalid or not found. "
        f"Max items: {VOUCHER_PAGE_SIZE}."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "One or more provided vouchers not found"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Validation error"},
    },
)
async def deactivate_vouchers(
    codes: Annotated[
        UniqueStrList,
        Field(
            max_length=VOUCHER_PAGE_SIZE,
            json_schema_extra={"minItems": 1, "uniqueItems": True},
        ),
    ],
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> None:
    patches = [
        VoucherUpdateRequest(
            code=code,
            status=VoucherStatus.INACTIVE,
        ).to_model()
        for code in codes
    ]

    existing_vouchers = await repo.get_many(codes)

    if len(existing_vouchers) != len(patches):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more provided vouchers not found",
        )

    await repo.update_many(patches)


@router.get(
    "/{code}",
    response_model=VoucherResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Voucher not found"}},
)
async def get_voucher_by_code(
    code: str, repo: AsyncVoucherRepository = Depends(get_repo)
) -> Voucher:
    voucher = await repo.get_by_code(code)
    if voucher is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voucher not found")
    return voucher


@router.get(
    "",
    response_model=list[VoucherResponse],
    status_code=status.HTTP_200_OK,
    description=f"List vouchers with pagination. Max page size: {VOUCHER_PAGE_SIZE}.",
)
async def get_vouchers(
    limit: int | None = Query(default=VOUCHER_PAGE_SIZE, gt=0, le=VOUCHER_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> list[Voucher]:
    vouchers = await repo.get_many(limit=limit, offset=offset)
    return vouchers


@router.patch(
    "",
    status_code=status.HTTP_200_OK,
    response_model=list[VoucherResponse],
    description=(
        "Update multiple vouchers in a single request. "
        "Fail-fast: the whole request is rejected if any item is invalid or not found. "
        f"Max items: {VOUCHER_UPDATE_LIMIT}."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "One or more provided vouchers not found"}
    },
)
async def update_vouchers(
    request: Annotated[
        ValidVoucherUpdateRequest,
        Field(
            max_length=VOUCHER_UPDATE_LIMIT,
            json_schema_extra={"minItems": 1},
        ),
    ],
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> list[Voucher]:
    # For simplicity, we avoid partial updates and fail the request if data is inconsistent

    try:
        patches = [patch.to_model() for patch in request]
    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    existing_vouchers = await repo.get_many(codes=[patch.code for patch in patches])

    if len(existing_vouchers) != len(patches):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more provided vouchers not found",
        )

    updated_vouchers = await repo.update_many(patches)
    return updated_vouchers
