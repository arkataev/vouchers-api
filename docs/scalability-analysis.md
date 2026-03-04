# Scalability Analysis

## Overview

This document analyses scalability bottlenecks in the vouchers-api under the following load profile:

- **Reads:** 1,000,000 requests/sec (`GET /vouchers/{code}`, `GET /vouchers`)
- **Writes:** Infrequent but bursty (`POST /vouchers`, `PATCH /vouchers`, `POST /vouchers/delete`, `PATCH /vouchers/deactivate`)

Bottlenecks are grouped by severity. Each entry references the relevant source file and line where applicable.

---

## Critical — Will fail under target load

### 1. SQLite database (`app/db.py:7`)

SQLite uses a single-writer lock. During any write operation, all concurrent reads block until the lock is released. At 1M RPS, even a 10ms write stall queues 10,000 requests.

Additionally, SQLite does not support horizontal scaling, connection pooling across processes, or read replicas.

**Fix:** Migrate to PostgreSQL with the `asyncpg` async driver. Read `DATABASE_URL` from an environment variable.

```python
# app/db.py
import os
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ["DATABASE_URL"]  # e.g. postgresql+asyncpg://...

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_timeout=10,
    pool_recycle=3600,
)
```

---

### 2. Single uvicorn worker (`Dockerfile`)

One Python process = one event loop. A single uvicorn worker tops out at approximately 5–15K RPS depending on payload size — roughly 100× below target.

**Fix:** Use gunicorn with `UvicornWorker` and set workers to `(CPU count × 2) + 1`. Deploy multiple containers behind a load balancer for horizontal scaling.

```dockerfile
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--workers", "9", "--bind", "0.0.0.0:8000"]
```

---

### 3. No caching layer

Every read request hits the database directly. Even with PostgreSQL and connection pooling, a single DB instance handles at most ~50–100K simple queries/sec. Serving 1M RPS from the DB alone is not feasible.

**Fix:** Add Redis as a read-through cache for point lookups (`GET /vouchers/{code}`). Use a short TTL (e.g. 60s) for list endpoints. Invalidate on every write.

For the hot-path read endpoint, return pre-serialized JSON from Redis directly, bypassing Pydantic serialization entirely:

```python
from fastapi import Response

@router.get("/{code}")
async def get_voucher_by_code(code: str, redis: Redis = Depends(get_redis)) -> Response:
    cached = await redis.get(f"voucher:{code}")
    if cached:
        return Response(content=cached, media_type="application/json")
    voucher = await repo.get_by_code(code)
    if voucher is None:
        raise HTTPException(status_code=404, detail="Voucher not found")
    serialized = VoucherResponse.model_validate(voucher).model_dump_json()
    await redis.setex(f"voucher:{code}", 60, serialized)
    return Response(content=serialized, media_type="application/json")
```

---

### 4. No connection pool configuration (`app/db.py:9`)

`create_async_engine(DATABASE_URL, future=True)` uses SQLAlchemy defaults (5 base connections). At 1M RPS with multiple workers, connection starvation occurs immediately.

**Fix:** Configure the pool explicitly (shown in fix #1 above). Additionally, deploy PgBouncer as an external connection pooler in front of PostgreSQL when running many app replicas.

---

## High — Will degrade severely under load

### 5. New repository and session factory per request (`app/vouchers/db/repository.py:134`)

```python
async def get_repo() -> AsyncVoucherRepository:
    return AsyncVoucherRepository(engine)
```

FastAPI's `Depends(get_repo)` creates a new `AsyncVoucherRepository` and a new `async_sessionmaker` on every request. At 1M RPS that is 1M unnecessary object allocations per second.

**Fix:** Make the repository a singleton using `@lru_cache`:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_repo() -> AsyncVoucherRepository:
    return AsyncVoucherRepository(engine)
```

---

### 6. Missing index on `created_at` (`app/vouchers/db/models.py`)

`GET /vouchers` orders results by `created_at` (`repository.py:75`). Without an index, every paginated list request performs a full table scan and in-memory sort.

**Fix:**

```python
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
```

---

### 7. Double DB round-trip in deactivate endpoint (`app/vouchers/api/http/v1/api.py:106`)

`PATCH /vouchers/deactivate` calls `repo.get_many(codes)` to verify existence, then `repo.update_many(patches)` — two separate transactions. This doubles write latency and introduces a race condition (a voucher could be deleted between the two calls).

`update_many` already performs an existence check internally with `SELECT ... FOR UPDATE`, making the pre-check redundant.

**Fix:** Remove the `get_many` pre-check and rely solely on `update_many`:

```python
@router.patch("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_vouchers(codes: ..., repo: AsyncVoucherRepository = Depends(get_repo)) -> None:
    patches = [VoucherUpdateRequest(code=code, status=VoucherStatus.INACTIVE).to_model() for code in codes]
    try:
        await repo.update_many(patches)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

---

### 8. Sequential `merge()` in `add_many` (`app/vouchers/db/repository.py:58`)

Each voucher in a batch issues a separate `SELECT` + `INSERT/UPDATE` (merge semantics). For a burst of 50 creates, that is up to 100 DB round-trips inside a single transaction.

**Fix:** Use `insert().values([...])` for a single round-trip. Since codes are auto-generated and unique, upsert semantics are not needed for creates:

```python
from sqlalchemy.dialects.postgresql import insert

async def add_many(self, vouchers: list[Voucher]) -> None:
    async with self._session_factory() as session:
        await session.execute(
            insert(VoucherORM),
            [self._to_orm(v).__dict__ for v in vouchers],
        )
        await session.commit()
```

---

### 9. No rate limiting or backpressure

A write burst with many concurrent requests will saturate the DB writer. Lock contention then cascades into read latency spikes across all workers.

**Fix:** Add rate limiting middleware (e.g. `slowapi`) with separate limits for read and write endpoints. Consider a write queue (Celery, ARQ, or a simple asyncio queue) for absorbing bursts.

---

## Medium — Will cause measurable performance degradation

### 10. No read replicas

A single database instance handles both 1M reads/sec and bursty writes. Even with Redis absorbing 90% of reads, 100K cache-miss reads/sec on one DB instance is high.

**Fix:** Configure PostgreSQL streaming replication with one or more read replicas. Route all `SELECT` queries to replicas and all writes to the primary. An acceptable read staleness of a few seconds is fine for list endpoints.

---

### 11. Offset-based pagination (`app/vouchers/api/http/v1/api.py:148`)

`OFFSET N LIMIT 100` requires the DB to scan and discard N rows before returning results. At large offsets this becomes a full table scan on every page request.

**Fix:** Switch to cursor-based pagination using the existing `created_at` index as the cursor:

```python
@router.get("")
async def get_vouchers(
    after_created_at: datetime | None = Query(default=None),
    after_code: str | None = Query(default=None),
    limit: int = Query(default=100, gt=0, le=100),
    repo: AsyncVoucherRepository = Depends(get_repo),
) -> list[VoucherResponse]:
    ...
```

---

### 12. No response compression

The list endpoint returns up to 100 vouchers (~15–20 KB of JSON per response). At 1M RPS, uncompressed responses generate ~15–20 GB/sec of egress.

**Fix:** Add gzip middleware (5–10× compression ratio on JSON):

```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

---

### 13. Pydantic serialization on every response

At 1M RPS, Pydantic model serialization adds non-trivial CPU overhead on the hot read path. This is addressed by the pre-serialized Redis cache described in fix #3.

---

## Low — Minor issues

### 14. Hardcoded `DATABASE_URL` (`app/db.py:7`)

Cannot configure different databases per environment without modifying source. Addressed in fix #1.

---

### 15. No health or readiness endpoints

Load balancers cannot determine whether an instance is healthy or ready to serve traffic, making rolling deployments and auto-recovery unreliable.

**Fix:** Add `GET /health` (liveness) and `GET /ready` (DB + Redis connectivity check) endpoints.

---

### 16. No structured logging or metrics

Latency percentiles, cache hit rates, and DB pool utilisation are invisible under load.

**Fix:** Expose Prometheus metrics (request latency histograms, cache hit/miss counters, DB pool gauges). Use structured JSON logging via `structlog`.

---

## Voucher code uniqueness at scale

The current code generator (`secrets.token_hex(6)`, 12 chars, 48 bits) is insufficient at scale. The birthday paradox gives a 50% collision probability at approximately 16M codes.

For multi-writer deployments, consider:

| Approach | Length | Entropy | Safe up to |
|----------|--------|---------|-----------|
| `token_hex(6)` (current) | 12 chars | 48 bits | ~1M codes |
| base64url of 9 UUID v7 bytes | 12 chars | 72 bits | ~1B codes |
| full UUID v7 in base62 | 22 chars | 128 bits | practically unlimited |

Regardless of the generation strategy, the `PRIMARY KEY` constraint on `code` is the authoritative uniqueness guarantee. Add retry logic in `add_many` to handle the rare `IntegrityError`:

```python
from sqlalchemy.exc import IntegrityError

async def add_many(self, vouchers: list[Voucher]) -> None:
    for attempt in range(5):
        try:
            async with self._session_factory() as session:
                ...
                await session.commit()
            return
        except IntegrityError:
            if attempt == 4:
                raise
            vouchers = [v.model_copy(update={"code": _generate_code()}) for v in vouchers]
```

---

## Remediation Priority

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| P0 | PostgreSQL + connection pool | Removes hard ceiling | Medium |
| P0 | Multi-worker deployment | 10–50× throughput | Low |
| P0 | Redis caching + pre-serialized responses | 10–100× read throughput | Medium |
| P1 | Singleton repository | Reduces allocation overhead | Low |
| P1 | `created_at` index | Faster list queries | Low |
| P1 | Fix deactivate double round-trip | Halves write latency, removes race | Low |
| P1 | Bulk insert in `add_many` | Faster batch creates | Low |
| P1 | Rate limiting | Prevents write cascades | Medium |
| P2 | Read replicas | Further read scaling | Medium |
| P2 | Cursor-based pagination | Eliminates deep-offset scans | Medium |
| P2 | Response compression | 5–10× bandwidth reduction | Low |
| P3 | Health/readiness endpoints | Operational reliability | Low |
| P3 | Metrics and structured logging | Observability | Medium |
