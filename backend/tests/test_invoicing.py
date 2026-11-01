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


def test_backdated_issue_blocked(api_client):
    cid = make_client(api_client)
    inv1 = make_invoice(api_client, cid)
    assert (
        post_json(
            api_client, f"/api/v1/invoices/{inv1['id']}/issue", {"issue_date": "2026-02-01"}
        ).status_code
        == 200
    )
    inv2 = make_invoice(api_client, cid)
    r = post_json(
        api_client, f"/api/v1/invoices/{inv2['id']}/issue", {"issue_date": "2026-01-15"}
    )
    assert r.status_code == 400
    assert "chronologija" in r.json()["detail"]
    # apėjimo nėra – ir su allow_backdated vėliavele
    r = post_json(
        api_client,
        f"/api/v1/invoices/{inv2['id']}/issue",
        {"issue_date": "2026-01-15", "allow_backdated": True},
    )
    assert r.status_code == 400
    # sprendimas: ankstesnė data su KITA serija – sukuriama nustatymuose
    assert post_json(api_client, "/api/v1/invoice-series", {"code": "SFK"}).status_code == 201
    r = post_json(
        api_client,
        f"/api/v1/invoices/{inv2['id']}/issue",
        {"issue_date": "2026-01-15", "series": "SFK"},
    )
    assert r.status_code == 200
    assert r.json()["issue_date"] == "2026-01-15"
    assert r.json()["full_number"].startswith("SFK-")


def test_backdated_edit_blocked(api_client):
    cid = make_client(api_client)
    inv1 = make_invoice(api_client, cid)
    post_json(
        api_client, f"/api/v1/invoices/{inv1['id']}/issue", {"issue_date": "2026-02-01"}
    )
    inv2 = make_invoice(api_client, cid)
    post_json(
        api_client, f"/api/v1/invoices/{inv2['id']}/issue", {"issue_date": "2026-02-10"}
    )
    r = api_client.put(
        f"/api/v1/invoices/{inv2['id']}",
        {
            "client_id": cid,
            "issue_date": "2026-01-20",
            "lines": [{"description": "X", "quantity": "1", "unit_price": "1.00"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "chronologija" in r.json()["detail"]


def test_invoice_series_crud(api_client):
    r = api_client.get("/api/v1/invoice-series")
    assert r.status_code == 200
    assert len(r.json()) == 1  # auto-sukuriama numatytoji
    assert r.json()[0]["is_default"]

    r = post_json(api_client, "/api/v1/invoice-series", {"code": "sfk"})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["code"] == "SFK"

    # nežinoma serija – 400
    cid = make_client(api_client)
    inv = make_invoice(api_client, cid)
    r = post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {"series": "ZZ"})
    assert r.status_code == 400

    # set-default
    assert api_client.post(f"/api/v1/invoice-series/{sid}/set-default").status_code == 200
    r = api_client.get("/api/v1/invoice-series").json()
    assert next(s for s in r if s["id"] == sid)["is_default"]

    # numatytosios trinti negalima
    assert api_client.delete(f"/api/v1/invoice-series/{sid}").status_code == 400


def test_no_tenant_403(client, user):
    client.force_login(user)  # vartotojas be veiklos
    client.cookies.load({"csrftoken": "x"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "x"
    assert client.get("/api/v1/clients").status_code == 403
