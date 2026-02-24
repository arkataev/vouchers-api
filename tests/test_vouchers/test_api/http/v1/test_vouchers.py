from datetime import datetime, timedelta, timezone

import pytest

from app.utils import TIME_ZONE, get_now
from app.vouchers.api.http.v1.api import (
    VOUCHER_CREATE_LIMIT,
    VOUCHER_PAGE_SIZE,
    VOUCHER_UPDATE_LIMIT,
)
from app.vouchers.model import Voucher, VoucherStatus


def create_voucher_payload(discount_percentage: int, valid_until: datetime) -> dict:
    return {
        "discount_percentage": discount_percentage,
        "valid_until": valid_until.isoformat(),
    }


class TestVouchersCreate:
    URL = "/v1/vouchers"

    @pytest.fixture(scope="class")
    def valid_expiration_date(self):
        return datetime.now(timezone.utc) + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)

    def test_create_vouchers_returns_201(self, client, valid_expiration_date):
        now = datetime.now(timezone.utc)
        discount_percentage = 15
        payload = [
            create_voucher_payload(discount_percentage, valid_expiration_date) for _ in range(3)
        ]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == len(payload)

        for voucher in data:
            assert voucher["code"] != ""
            assert voucher["discount_percentage"] == discount_percentage < 100
            assert datetime.fromisoformat(voucher["valid_until"]) == valid_expiration_date
            assert voucher["status"] == "active"

            created_at = datetime.fromisoformat(voucher["created_at"])
            assert now <= created_at <= datetime.now(timezone.utc)

            expiration_date = datetime.fromisoformat(voucher["valid_until"])
            assert expiration_date > now

    @pytest.mark.parametrize(
        "invalid_expiration_date",
        [
            get_now() - timedelta(days=1),
            get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS + 1),
            "invalid_date",
        ],
        ids=[
            "invalid_expiration_date",
            "future_expiration_date",
            "invalid_date_format",
        ],
    )
    def test_create_vouchers_invalid_expiration_data_returns_status_422(
        self, client, invalid_expiration_date
    ):
        discount_percentage = 15
        if isinstance(invalid_expiration_date, datetime):
            payload = [create_voucher_payload(discount_percentage, invalid_expiration_date)]
        else:
            payload = [
                {
                    "discount_percentage": discount_percentage,
                    "valid_until": invalid_expiration_date,
                }
            ]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 422

    def test_create_vouchers_without_discount_percentage(self, client, valid_expiration_date):
        payload = [{"valid_until": valid_expiration_date.isoformat()}]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "discount_percentage",
        [
            101,
            -1,
            "invalid_type",
            1.1,
        ],
        ids=["over_hundred", "negative", "invalid_type", "float_value"],
    )
    def test_create_vouchers_with_invalid_discount_percentage_return_422(
        self, client, discount_percentage, valid_expiration_date
    ):
        payload = [create_voucher_payload(discount_percentage, valid_expiration_date)]
        response = client.post(self.URL, json=payload)
        assert response.status_code == 422

    def test_create_voucher_with_pre_set_status(self, client):
        valid_until = get_now() + timedelta(days=7)
        payload = [
            {
                "discount_percentage": 25,
                "valid_until": valid_until.isoformat(),
                "status": VoucherStatus.INACTIVE,
            }
        ]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == VoucherStatus.INACTIVE

    def test_create_voucher_with_invalid_status(self, client, valid_expiration_date):
        payload = [
            {
                "discount_percentage": 25,
                "valid_until": valid_expiration_date.isoformat(),
                "status": "my-status",
            }
        ]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 422

    def test_create_voucher_without_valid_until(self, client):
        payload = [{"discount_percentage": 10}]
        response = client.post(self.URL, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert datetime.fromisoformat(data[0]["valid_until"]) <= get_now() + timedelta(
            days=Voucher.MAX_VALIDITY_DAYS
        )

    def test_create_voucher_default_status_is_active(self, client, valid_expiration_date):
        payload = [
            {
                "discount_percentage": 20,
                "valid_until": valid_expiration_date.isoformat(),
            }
        ]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == VoucherStatus.ACTIVE

    def test_create_voucher_normalizes_naive_valid_until_to_utc(self, client):
        naive_valid_until = datetime.now() + timedelta(days=7)
        payload = [{"discount_percentage": 30, "valid_until": naive_valid_until.isoformat()}]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        returned_valid_until = datetime.fromisoformat(data[0]["valid_until"])
        assert returned_valid_until.tzinfo is not None
        assert returned_valid_until == naive_valid_until.replace(tzinfo=TIME_ZONE)

    def test_create_voucher_converts_valid_until_to_utc(self, client):
        valid_until = datetime.now(timezone(timedelta(hours=2))) + timedelta(days=7)
        payload = [{"discount_percentage": 35, "valid_until": valid_until.isoformat()}]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 1
        returned_valid_until = datetime.fromisoformat(data[0]["valid_until"])
        assert returned_valid_until.tzinfo is not None
        assert returned_valid_until == valid_until.astimezone(TIME_ZONE)

    def test_create_vouchers_over_limit_returns_422(self, client):
        valid_until = get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)
        payload = [create_voucher_payload(10, valid_until) for _ in range(VOUCHER_CREATE_LIMIT + 1)]

        response = client.post(self.URL, json=payload)

        assert response.status_code == 422


class TestVouchersGet:

    URL = "/v1/vouchers"

    @pytest.fixture()
    def valid_expiration_date(self):
        return get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)

    def test_get_voucher_by_code(self, client, valid_expiration_date):
        payload = [create_voucher_payload(15, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.get(f"{self.URL}/{created['code']}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == created["code"]
        assert data["discount_percentage"] == created["discount_percentage"]
        assert data["valid_until"] == created["valid_until"]
        assert data["status"] == created["status"]

    def test_get_voucher_by_code_not_found(self, client):
        response = client.get(f"{self.URL}/missing-code")

        assert response.status_code == 404

    def test_get_vouchers(self, client, valid_expiration_date):
        payload = [
            create_voucher_payload(10, valid_expiration_date),
            create_voucher_payload(20, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        created_codes = {voucher["code"] for voucher in created}

        response = client.get(self.URL)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        response_codes = {voucher["code"] for voucher in data}
        assert created_codes.issubset(response_codes)

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": -1},
            {"offset": -1},
            {"limit": "invalid"},
            {"offset": "invalid"},
        ],
        ids=[
            "limit_zero",
            "limit_negative",
            "offset_negative",
            "limit_invalid",
            "offset_invalid",
        ],
    )
    def test_get_vouchers_invalid_pagination_returns_422(self, client, params):
        response = client.get(self.URL, params=params)

        assert response.status_code == 422

    def test_get_vouchers_pagination_out_of_range_returns_empty(
        self, client, valid_expiration_date
    ):
        payload = [
            create_voucher_payload(5, valid_expiration_date),
            create_voucher_payload(15, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201

        response = client.get(self.URL, params={"limit": 10, "offset": 1000})

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_get_vouchers_pagination(self, client, valid_expiration_date):
        payload = [
            create_voucher_payload(5, valid_expiration_date),
            create_voucher_payload(15, valid_expiration_date),
            create_voucher_payload(25, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        created_codes = [voucher["code"] for voucher in created]

        first_page = client.get(self.URL, params={"limit": 2, "offset": 0})
        assert first_page.status_code == 200
        first_page_data = first_page.json()
        assert isinstance(first_page_data, list)
        assert len(first_page_data) == 2

        second_page = client.get(self.URL, params={"limit": 2, "offset": 2})
        assert second_page.status_code == 200
        second_page_data = second_page.json()
        assert isinstance(second_page_data, list)
        assert len(second_page_data) == 1

        paged_codes = [voucher["code"] for voucher in first_page_data + second_page_data]
        assert set(created_codes) == set(paged_codes)


class TestVouchersUpdate:

    URL = "/v1/vouchers"

    @pytest.fixture()
    def valid_expiration_date(self):
        return get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)

    def test_update_vouchers(self, client, valid_expiration_date):
        payload = [
            create_voucher_payload(10, valid_expiration_date),
            create_voucher_payload(20, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()

        update_payload = [
            {"code": created[0]["code"], "discount_percentage": 30},
            {"code": created[1]["code"], "status": VoucherStatus.INACTIVE},
        ]
        response = client.patch(self.URL, json=update_payload)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        updated_by_code = {voucher["code"]: voucher for voucher in data}
        assert updated_by_code[created[0]["code"]]["discount_percentage"] == 30
        assert updated_by_code[created[1]["code"]]["status"] == VoucherStatus.INACTIVE

    def test_update_vouchers_partial_update_keeps_other_fields(self, client, valid_expiration_date):
        payload = [create_voucher_payload(15, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        update_payload = [{"code": created["code"], "status": VoucherStatus.INACTIVE}]
        response = client.patch(self.URL, json=update_payload)

        assert response.status_code == 200
        updated = response.json()[0]
        assert updated["status"] == VoucherStatus.INACTIVE
        assert updated["discount_percentage"] == created["discount_percentage"]
        assert updated["valid_until"] == created["valid_until"]

    def test_update_vouchers_status_transition_both_ways(self, client, valid_expiration_date):
        payload = [create_voucher_payload(25, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        to_inactive = client.patch(
            self.URL, json=[{"code": created["code"], "status": VoucherStatus.INACTIVE}]
        )
        assert to_inactive.status_code == 200
        assert to_inactive.json()[0]["status"] == VoucherStatus.INACTIVE

        to_active = client.patch(
            self.URL, json=[{"code": created["code"], "status": VoucherStatus.ACTIVE}]
        )
        assert to_active.status_code == 200
        assert to_active.json()[0]["status"] == VoucherStatus.ACTIVE

    def test_update_vouchers_not_found_fails_fast(self, client):
        response = client.patch(
            self.URL, json=[{"code": "missing-code", "discount_percentage": 10}]
        )

        assert response.status_code == 404

    def test_update_vouchers_with_duplicate_codes_fails(self, client, valid_expiration_date):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        update_payload = [
            {"code": created["code"], "discount_percentage": 30},
            {"code": created["code"], "discount_percentage": 40},
        ]
        response = client.patch(self.URL, json=update_payload)

        assert response.status_code == 422

    def test_update_vouchers_empty_list(self, client):
        response = client.patch(self.URL, json=[])

        assert response.status_code == 422

    def test_update_vouchers_missing_code(self, client):
        response = client.patch(self.URL, json=[{"discount_percentage": 10}])

        assert response.status_code == 422

    def test_update_vouchers_without_update_fields(self, client):
        response = client.patch(self.URL, json=[{"code": "some-code"}])

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "payload_item",
        [
            {"code": "code-1", "discount_percentage": -1},
            {"code": "code-1", "discount_percentage": 101},
            {"code": "code-1", "discount_percentage": "invalid"},
            {"code": "code-1", "discount_percentage": 1.1},
        ],
        ids=["discount_zero", "discount_over", "discount_invalid", "discount_float"],
    )
    def test_update_vouchers_invalid_discount_percentage(
        self, client, payload_item, valid_expiration_date
    ):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]
        payload_item["code"] = created["code"]

        response = client.patch(self.URL, json=[payload_item])

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "invalid_valid_until",
        [
            (get_now() - timedelta(days=1)).isoformat(),
            (get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS + 1)).isoformat(),
            "invalid_date",
        ],
        ids=["past_date", "beyond_max", "invalid_format"],
    )
    def test_update_vouchers_invalid_valid_until(
        self, client, invalid_valid_until, valid_expiration_date
    ):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.patch(
            self.URL,
            json=[{"code": created["code"], "valid_until": invalid_valid_until}],
        )

        assert response.status_code == 422

    def test_update_vouchers_invalid_status(self, client, valid_expiration_date):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.patch(
            self.URL, json=[{"code": created["code"], "status": "invalid-status"}]
        )

        assert response.status_code == 422

    def test_update_vouchers_mixed_valid_and_invalid_fails_fast(
        self, client, valid_expiration_date
    ):
        payload = [
            create_voucher_payload(10, valid_expiration_date),
            create_voucher_payload(20, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()

        update_payload = [
            {"code": created[0]["code"], "discount_percentage": 30},
            {"code": "missing-code", "discount_percentage": 40},
        ]
        response = client.patch(self.URL, json=update_payload)

        assert response.status_code == 404

    def test_update_vouchers_over_limit_returns_422(self, client):
        update_payload = [
            {"code": f"code-{idx}", "discount_percentage": 10}
            for idx in range(VOUCHER_UPDATE_LIMIT + 1)
        ]

        response = client.patch(self.URL, json=update_payload)

        assert response.status_code == 422


class TestVouchersDelete:
    URL = "/v1/vouchers"

    @pytest.fixture()
    def valid_expiration_date(self):
        return get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)

    def test_delete_vouchers(self, client, valid_expiration_date):
        payload = [
            create_voucher_payload(10, valid_expiration_date),
            create_voucher_payload(20, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        codes = [voucher["code"] for voucher in created]

        delete_response = client.post(f"{self.URL}/delete", json=codes)

        assert delete_response.status_code == 204
        for code in codes:
            get_response = client.get(f"{self.URL}/{code}")
            assert get_response.status_code == 404

    def test_delete_vouchers_not_found(self, client):
        response = client.post(f"{self.URL}/delete", json=["missing-code"])

        assert response.status_code == 404

    def test_delete_vouchers_mixed_valid_and_invalid_fails_fast(
        self, client, valid_expiration_date
    ):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.post(f"{self.URL}/delete", json=[created["code"], "missing-code"])

        assert response.status_code == 404

    def test_delete_vouchers_with_duplicate_codes(self, client, valid_expiration_date):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.post(f"{self.URL}/delete", json=[created["code"], created["code"]])

        assert response.status_code == 422

    def test_delete_vouchers_empty_list(self, client):
        response = client.post(f"{self.URL}/delete", json=[])

        assert response.status_code == 422

    def test_delete_vouchers_invalid_payload(self, client):
        response = client.post(f"{self.URL}/delete", json=[{"code": "some-code"}])

        assert response.status_code == 422

    def test_delete_vouchers_over_limit_returns_422(self, client):
        codes = [f"code-{idx}" for idx in range(VOUCHER_PAGE_SIZE + 1)]
        response = client.post(f"{self.URL}/delete", json=codes)

        assert response.status_code == 422


class TestVouchersDeactivate:
    URL = "/v1/vouchers"

    @pytest.fixture()
    def valid_expiration_date(self):
        return get_now() + timedelta(days=Voucher.MAX_VALIDITY_DAYS - 1)

    def test_deactivate_vouchers(self, client, valid_expiration_date):
        payload = [
            create_voucher_payload(10, valid_expiration_date),
            create_voucher_payload(20, valid_expiration_date),
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()
        codes = [voucher["code"] for voucher in created]

        response = client.patch(f"{self.URL}/deactivate", json=codes)

        assert response.status_code == 204
        for code in codes:
            get_response = client.get(f"{self.URL}/{code}")
            assert get_response.status_code == 200
            assert get_response.json()["status"] == VoucherStatus.INACTIVE

    def test_deactivate_vouchers_already_inactive(self, client, valid_expiration_date):
        payload = [
            {
                "discount_percentage": 10,
                "valid_until": valid_expiration_date.isoformat(),
                "status": VoucherStatus.INACTIVE,
            }
        ]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.patch(f"{self.URL}/deactivate", json=[created["code"]])

        assert response.status_code == 204
        get_response = client.get(f"{self.URL}/{created['code']}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == VoucherStatus.INACTIVE

    def test_deactivate_vouchers_not_found(self, client):
        response = client.patch(f"{self.URL}/deactivate", json=["missing-code"])

        assert response.status_code == 404

    def test_deactivate_vouchers_mixed_valid_and_invalid_fails_fast(
        self, client, valid_expiration_date
    ):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.patch(f"{self.URL}/deactivate", json=[created["code"], "missing-code"])

        assert response.status_code == 404

    def test_deactivate_vouchers_with_duplicate_codes(self, client, valid_expiration_date):
        payload = [create_voucher_payload(10, valid_expiration_date)]
        create_response = client.post(self.URL, json=payload)
        assert create_response.status_code == 201
        created = create_response.json()[0]

        response = client.patch(f"{self.URL}/deactivate", json=[created["code"], created["code"]])

        assert response.status_code == 422

    def test_deactivate_vouchers_empty_list(self, client):
        response = client.patch(f"{self.URL}/deactivate", json=[])

        assert response.status_code == 422

    def test_deactivate_vouchers_invalid_payload(self, client):
        response = client.patch(f"{self.URL}/deactivate", json=[{"code": "some-code"}])

        assert response.status_code == 422

    def test_deactivate_vouchers_over_limit_returns_422(self, client):
        codes = [f"code-{idx}" for idx in range(VOUCHER_PAGE_SIZE + 1)]
        response = client.patch(f"{self.URL}/deactivate", json=codes)

        assert response.status_code == 422
