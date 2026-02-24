# Voucher Service

## Purpose
The service provides a minimal voucher management API. It supports creating, listing, updating, deactivating, and deleting voucher codes with validation rules around discount percentage and expiration date.

## Main API
Base path: `/v1`

API docs (Redoc): `http://localhost:8000/redoc`

Endpoints:
- `POST /v1/vouchers` Create up to 50 vouchers in a single request (fail-fast validation).
- `GET /v1/vouchers` List vouchers with pagination (`limit` and `offset`, max page size 100).
- `GET /v1/vouchers/{code}` Fetch a voucher by its code.
- `PATCH /v1/vouchers` Update up to 50 vouchers in a single request (fail-fast validation).
- `PATCH /v1/vouchers/deactivate` Deactivate vouchers by code (fail-fast validation).
- `POST /v1/vouchers/delete` Delete vouchers by code (fail-fast validation).

Notes:
- `discount_percentage` must be between 1 and 100.
- `valid_until` is optional. If omitted, it defaults to `now + 365 days`.
- `valid_until` must be in the future and not more than 365 days from now.
- Voucher `code` is generated automatically on creation.

## Install And Run (Make)

Local development:
1. Ensure Python 3.12 is available and dependencies are installed (for example via `poetry install` or `pip install -e .`).
2. Run the API locally:

```bash
make run
```

Dockerized run:

```bash
make docker-build
make docker-run
```

Other useful commands:

```bash
make test
make lint
```

## Example Payloads (Create Vouchers)

Create a single voucher:

```json
[
  {
    "discount_percentage": 15,
    "valid_until": "2026-12-31T23:59:59Z",
    "status": "active"
  }
]
```

## Example Payloads (Deactivate Vouchers)

Deactivate by code list:

```json
[
  "a1b2c3d4e5f6",
  "f6e5d4c3b2a1"
]
```

## Example Payloads (Delete Vouchers)

Delete by code list:

```json
[
  "a1b2c3d4e5f6",
  "f6e5d4c3b2a1"
]
```

Create multiple vouchers (status/valid_until optional):

```json
[
  {
    "discount_percentage": 10
  },
  {
    "discount_percentage": 25,
    "valid_until": "2026-08-01T00:00:00Z"
  },
  {
    "discount_percentage": 5,
    "status": "inactive"
  }
]
```
