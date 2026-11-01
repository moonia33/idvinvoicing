import pytest
from django.test import Client

from apps.tenancy.models import SellerProfile
from tests.conftest import post_json


@pytest.fixture
def supplier(api_client: Client):
    resp = post_json(api_client, "/api/v1/suppliers", {"name": "UAB Tiekėjas", "code": "301"})
    assert resp.status_code == 201, resp.content
    return resp.json()


@pytest.fixture
def purchase(api_client: Client, supplier):
    resp = post_json(
        api_client,
        "/api/v1/purchases",
        {
            "supplier_id": supplier["id"],
            "doc_number": "SF-PL-55",
            "document_date": "2026-01-10",
            "lines": [
                {"description": "Detalės", "quantity": "2", "unit_price": "50.00"},
                {"description": "Pristatymas", "quantity": "1", "unit_price": "20.00"},
            ],
        },
    )
    assert resp.status_code == 201, resp.content
    return resp.json()


def test_supplier_crud_and_isolation(api_client, other_tenant, client, other_user, supplier):
    r = api_client.get("/api/v1/suppliers")
    assert len(r.json()) == 1
    # kitas tenant nemato
    client.force_login(other_user)
    client.cookies.load({"csrftoken": "x"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "x"
    post_json(client, "/api/v1/tenants/switch", {"tenant_id": other_tenant.id})
    assert client.get("/api/v1/suppliers").json() == []


def test_purchase_total_and_status(api_client, purchase):
    assert purchase["total"] == "120.00"
    assert purchase["total_eur"] == "120.00"
    assert purchase["status"] == "received"


def test_partial_payment_status(api_client, purchase):
    resp = post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {"amount_original": "50.00", "paid_at": "2026-01-15", "method": "bank"},
    )
    assert resp.status_code == 201, resp.content
    p = api_client.get(f"/api/v1/purchases/{purchase['id']}").json()
    assert p["status"] == "partially_paid"
    assert p["paid_total"] == "50.00"


def test_full_payment_status(api_client, purchase):
    post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {"amount_original": "120.00", "paid_at": "2026-01-15"},
    )
    p = api_client.get(f"/api/v1/purchases/{purchase['id']}").json()
    assert p["status"] == "paid"


def test_kio_auto_number(api_client, purchase):
    r1 = post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {
            "amount_original": "60.00",
            "paid_at": "2026-01-15",
            "method": "cash",
            "doc_type": "kio",
        },
    )
    assert r1.json()["doc_number"] == "KIO-2026-0001"
    r2 = post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {
            "amount_original": "60.00",
            "paid_at": "2026-01-16",
            "method": "cash",
            "doc_type": "kio",
        },
    )
    assert r2.json()["doc_number"] == "KIO-2026-0002"


def test_ppk_manual_number(api_client, purchase):
    r = post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {
            "amount_original": "120.00",
            "paid_at": "2026-01-15",
            "method": "cash",
            "doc_type": "ppk",
            "doc_number": "TIEKEJO-PPK-77",
        },
    )
    assert r.json()["doc_number"] == "TIEKEJO-PPK-77"


def test_pln_purchase_eur_conversion(api_client, supplier):
    resp = post_json(
        api_client,
        "/api/v1/purchases",
        {
            "supplier_id": supplier["id"],
            "doc_number": "FV-9",
            "document_date": "2026-02-01",
            "currency": "PLN",
            "exchange_rate": "0.2345",
            "lines": [{"description": "Prekės", "quantity": "1", "unit_price": "1000.00"}],
        },
    )
    p = resp.json()
    assert p["total"] == "1000.00"
    assert p["total_eur"] == "234.50"
    # mokėjimas kitu kursu (kita data – kitas kursas)
    r = post_json(
        api_client,
        f"/api/v1/purchases/{p['id']}/payments",
        {
            "amount_original": "500.00",
            "exchange_rate": "0.24",
            "paid_at": "2026-02-05",
        },
    )
    assert r.json()["amount_eur"] == "120.00"


def test_journal_cash_basis(api_client, tenant, purchase):
    """Pinigų principu: išlaidos žurnale mokėjimo dieną."""
    tenant.profile.accounting_basis = SellerProfile.AccountingBasis.CASH
    tenant.profile.save()
    post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {"amount_original": "60.00", "paid_at": "2026-01-15"},
    )
    j = api_client.get("/api/v1/ledger/journal?year=2026&month=1").json()
    exp = [r for r in j["rows"] if r["kind"] == "expense" and r["source"] == "purchase"]
    assert len(exp) == 1
    assert exp[0]["amount"] == "60.00"
    assert exp[0]["date"] == "2026-01-15"
    assert exp[0]["counterparty"] == "UAB Tiekėjas"


def test_journal_accrual_basis(api_client, tenant, purchase):
    """Kaupimo principu: išlaidos dokumento dieną visa suma."""
    tenant.profile.accounting_basis = SellerProfile.AccountingBasis.ACCRUAL
    tenant.profile.save()
    j = api_client.get("/api/v1/ledger/journal?year=2026&month=1").json()
    exp = [r for r in j["rows"] if r["kind"] == "expense" and r["source"] == "purchase"]
    assert len(exp) == 1
    assert exp[0]["amount"] == "120.00"
    assert exp[0]["date"] == "2026-01-10"


def test_kio_pdf(api_client, purchase, monkeypatch):
    monkeypatch.setattr(
        "apps.purchases.api.generate_kio_pdf", lambda p: b"%PDF-kio"
    )
    r = post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {
            "amount_original": "120.00",
            "paid_at": "2026-01-15",
            "method": "cash",
            "doc_type": "kio",
        },
    )
    pid = r.json()["id"]
    pdf = api_client.get(f"/api/v1/purchase-payments/{pid}/kio.pdf")
    assert pdf.status_code == 200
    assert pdf.content == b"%PDF-kio"


def test_cancel_rules(api_client, purchase):
    post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {"amount_original": "10.00", "paid_at": "2026-01-15"},
    )
    r = api_client.post(f"/api/v1/purchases/{purchase['id']}/cancel")
    assert r.status_code == 200  # anuliuojama kartu su mokėjimais
    assert r.json()["payments"] == []


def test_edit_after_payment(api_client, purchase):
    post_json(
        api_client,
        f"/api/v1/purchases/{purchase['id']}/payments",
        {"amount_original": "10.00", "paid_at": "2026-01-15"},
    )
    r = api_client.put(
        f"/api/v1/purchases/{purchase['id']}",
        {
            "supplier_id": purchase["supplier"]["id"],
            "document_date": "2026-01-11",
            "lines": [{"description": "X", "quantity": "1", "unit_price": "1.00"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"  # mokėjimas 10 >= nauja suma 1


def test_paid_now_creates_payment(api_client, supplier):
    r = api_client.post(
        "/api/v1/purchases",
        {
            "supplier_id": supplier["id"],
            "doc_type": "receipt",
            "doc_number": "KV-777",
            "document_date": "2026-02-01",
            "paid_now": True,
            "lines": [{"description": "Prekės", "quantity": "1", "unit_price": "25.00"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "paid"
    assert len(body["payments"]) == 1
    p = body["payments"][0]
    assert p["method"] == "cash"
    assert p["amount_original"] == "25.00"
    assert p["doc_number"] == "KV-777"


def test_paid_now_bank_transfer(api_client, supplier):
    r = api_client.post(
        "/api/v1/purchases",
        {
            "supplier_id": supplier["id"],
            "doc_type": "sf",
            "doc_number": "INV-9",
            "document_date": "2026-02-02",
            "paid_now": True,
            "paid_method": "bank",
            "paid_doc_number": "OP-123",
            "lines": [{"description": "Paslauga", "quantity": "1", "unit_price": "50.00"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 201
    p = r.json()["payments"][0]
    assert p["method"] == "bank"
    assert p["doc_number"] == "OP-123"


def test_paid_now_kio_autonumber(api_client, supplier):
    r = api_client.post(
        "/api/v1/purchases",
        {
            "supplier_id": supplier["id"],
            "doc_type": "kio",
            "document_date": "2026-02-01",
            "paid_now": True,
            "lines": [{"description": "X", "quantity": "1", "unit_price": "5.00"}],
        },
        content_type="application/json",
    )
    assert r.status_code == 201
    assert r.json()["payments"][0]["doc_type"] == "kio"
    assert r.json()["payments"][0]["doc_number"].startswith("KIO-")
