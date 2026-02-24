from fastapi import APIRouter

from app.vouchers.api.http.v1.api import router as vouchers_router

router = APIRouter(prefix="/v1")
router.include_router(vouchers_router)
