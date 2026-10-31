import io

import pytest
from PIL import Image

from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 200), "red").save(buf, format="PNG")
    return buf.getvalue()


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


def test_change_password(api_client, user):
    resp = post_json(
        api_client,
        "/api/v1/auth/password",
        {"old_password": "blogas", "new_password": "naujas123"},
    )
    assert resp.status_code == 400

    resp = post_json(
        api_client,
        "/api/v1/auth/password",
        {"old_password": "slaptas123", "new_password": "trumpas"},
    )
    assert resp.status_code == 400

    resp = post_json(
        api_client,
        "/api/v1/auth/password",
        {"old_password": "slaptas123", "new_password": "naujas12345"},
    )
    assert resp.status_code == 200
    # sesija išlieka (update_session_auth_hash), nauju slaptažodžiu veikia login
    assert api_client.get("/api/v1/auth/me").status_code == 200
    user.refresh_from_db()
    assert user.check_password("naujas12345")


def test_profile_logo_upload_and_delete(api_client, tenant):
    resp = api_client.post(
        "/api/v1/profile/logo", {"file": io.BytesIO(_png())}, format="multipart"
    )
    assert resp.status_code == 200
    logo = resp.json()["logo"]
    assert logo.startswith("data:image/png;base64,")
    assert api_client.get("/api/v1/profile").json()["logo"] == logo

    resp = api_client.post("/api/v1/profile/logo", {"file": io.BytesIO(b"abc")})
    assert resp.status_code == 400

    resp = api_client.delete("/api/v1/profile/logo")
    assert resp.status_code == 200
    assert resp.json()["logo"] == ""
