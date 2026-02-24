from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import dispose_db, init_db
from app.router import router as v1_router


@asynccontextmanager
async def lifespan(app):
    await init_db()
    try:
        yield
    finally:
        await dispose_db()


app = FastAPI(lifespan=lifespan)

app.include_router(v1_router)
