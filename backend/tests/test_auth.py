import pytest

from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_login_wrong_password(client, user):
    resp = post_json(client, "/api/v1/auth/login", {"username": "tomas", "password": "blogai"})
    assert resp.status_code == 401


def test_login_and_me(client, user, tenant):
    resp = post_json(client, "/api/v1/auth/login", {"username": "tomas", "password": "slaptas123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "tomas"
    assert data["current_tenant_id"] == tenant.id
    assert data["tenants"][0]["name"] == "IT konsultacijos"


def test_me_unauthenticated(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_create_and_switch_tenant(api_client, user, tenant, other_tenant):
    resp = api_client.get("/api/v1/auth/me")
    assert resp.json()["current_tenant_id"] == tenant.id

    resp = post_json(api_client, "/api/v1/tenants/switch", {"tenant_id": other_tenant.id})
    assert resp.status_code == 403

    resp = post_json(api_client, "/api/v1/tenants", {"name": "Antra veikla"})
    assert resp.status_code == 200
    new_id = resp.json()["id"]

    resp = post_json(api_client, "/api/v1/tenants/switch", {"tenant_id": new_id})
    assert resp.status_code == 200
    assert api_client.get("/api/v1/auth/me").json()["current_tenant_id"] == new_id


def test_profile_upsert(api_client, tenant):
    resp = api_client.put(
        "/api/v1/profile",
        {"seller_name": "Tomas IV", "iban": "LT999", "accounting_basis": "accrual"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["iban"] == "LT999"
    assert api_client.get("/api/v1/profile").json()["accounting_basis"] == "accrual"
