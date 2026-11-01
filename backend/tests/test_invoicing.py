import pytest

from tests.conftest import post_json

pytestmark = pytest.mark.django_db

INVOICE = {
    "due_date": "2026-01-15",
    "notes": "Testas",
    "lines": [
        {
            "description": "Programavimo paslaugos",
            "quantity": "10",
            "unit": "val.",
            "unit_price": "50.00",
        },
        {"description": "Konsultacija", "quantity": "1", "unit_price": "100.00"},
    ],
}


def make_client(api_client):
    resp = post_json(api_client, "/api/v1/clients", {"name": "UAB Klientas", "code": "123"})
    assert resp.status_code == 201
    return resp.json()["id"]


def make_invoice(api_client, client_id):
    resp = post_json(api_client, "/api/v1/invoices", {**INVOICE, "client_id": client_id})
    assert resp.status_code == 201
    return resp.json()


def test_client_crud(api_client):
    cid = make_client(api_client)
    resp = api_client.put(
        f"/api/v1/clients/{cid}",
        {"name": "UAB Klientas", "email": "a@b.lt"},
        content_type="application/json",
    )
    assert resp.json()["email"] == "a@b.lt"
    assert api_client.delete(f"/api/v1/clients/{cid}").status_code == 204


def test_tenant_isolation(api_client, client, other_user, other_tenant):
    cid = make_client(api_client)
    # kitas vartotojas neturi matyti mūsų kliento
    client.force_login(other_user)
    client.cookies.load({"csrftoken": "x"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "x"
    assert client.get(f"/api/v1/clients/{cid}").status_code == 404
    assert client.get("/api/v1/clients").json() == []


def test_invoice_lifecycle(api_client):
    cid = make_client(api_client)
    inv = make_invoice(api_client, cid)
    assert inv["status"] == "draft"
    assert inv["total"] == "600.00"
    assert inv["full_number"] is None

    resp = post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {})
    assert resp.status_code == 200
    inv = resp.json()
    assert inv["status"] == "issued"
    assert inv["full_number"].startswith("SF-") and inv["number"] == 1

    # dalinis mokėjimas
    resp = post_json(
        api_client,
        f"/api/v1/invoices/{inv['id']}/payments",
        {"amount": "200.00", "paid_at": "2026-01-10", "method": "bank"},
    )
    assert resp.status_code == 201
    assert api_client.get(f"/api/v1/invoices/{inv['id']}").json()["status"] == "partially_paid"

    # pilnas apmokėjimas
    post_json(
        api_client,
        f"/api/v1/invoices/{inv['id']}/payments",
        {"amount": "400.00", "paid_at": "2026-01-12", "method": "bank"},
    )
    assert api_client.get(f"/api/v1/invoices/{inv['id']}").json()["status"] == "paid"


def test_invoice_numbering_sequential(api_client):
    cid = make_client(api_client)
    n1 = post_json(
        api_client, f"/api/v1/invoices/{make_invoice(api_client, cid)['id']}/issue", {}
    ).json()["number"]
    n2 = post_json(
        api_client, f"/api/v1/invoices/{make_invoice(api_client, cid)['id']}/issue", {}
    ).json()["number"]
    assert (n1, n2) == (1, 2)


def test_invoice_requires_lines(api_client):
    cid = make_client(api_client)
    resp = post_json(api_client, "/api/v1/invoices", {"client_id": cid, "lines": []})
    assert resp.status_code == 400


def test_cancel_rules(api_client):
    cid = make_client(api_client)
    inv = make_invoice(api_client, cid)
    post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {})
    assert post_json(api_client, f"/api/v1/invoices/{inv['id']}/cancel", {}).status_code == 200

    inv2 = make_invoice(api_client, cid)
    post_json(api_client, f"/api/v1/invoices/{inv2['id']}/issue", {})
    post_json(
        api_client,
        f"/api/v1/invoices/{inv2['id']}/payments",
        {"amount": "600.00", "paid_at": "2026-01-10", "method": "bank"},
    )
    r = post_json(api_client, f"/api/v1/invoices/{inv2['id']}/cancel", {})
    assert r.status_code == 200  # anuliuojama kartu su mokėjimais
    assert r.json()["payments"] == []


def test_no_tenant_403(client, user):
    client.force_login(user)  # vartotojas be veiklos
    client.cookies.load({"csrftoken": "x"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "x"
    assert client.get("/api/v1/clients").status_code == 403
