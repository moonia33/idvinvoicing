import pytest

from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def make_invoice_paid(api_client, client_id, issue="2026-01-10", paid="2026-02-05"):
    resp = post_json(
        api_client,
        "/api/v1/invoices",
        {
            "client_id": client_id,
            "lines": [{"description": "Paslauga", "quantity": "1", "unit_price": "500.00"}],
        },
    )
    inv = resp.json()
    post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {"issue_date": issue})
    post_json(
        api_client,
        f"/api/v1/invoices/{inv['id']}/payments",
        {"amount": "500.00", "paid_at": paid, "method": "bank"},
    )
    return inv


def test_pln_conversion(api_client):
    resp = post_json(
        api_client,
        "/api/v1/ledger/entries",
        {
            "kind": "expense",
            "document_date": "2026-01-15",
            "counterparty": "Allegro",
            "currency": "PLN",
            "amount_original": "229.00",
            "exchange_rate": "0.235",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["amount_eur"] == "53.82"


def test_journal_cash_basis(api_client, tenant):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    make_invoice_paid(api_client, cid)  # issued sausį, apmokėta vasarį

    jan = api_client.get("/api/v1/ledger/journal?year=2026&month=1").json()
    feb = api_client.get("/api/v1/ledger/journal?year=2026&month=2").json()
    assert jan["income_total"] == "0.00"  # pinigų principas – pajamos tik vasarį
    assert feb["income_total"] == "500.00"


def test_journal_whole_year(api_client, tenant):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    make_invoice_paid(api_client, cid)  # apmokėta vasarį
    year = api_client.get("/api/v1/ledger/journal?year=2026&month=0").json()
    assert year["income_total"] == "500.00"
    assert len(year["rows"]) == 1
    assert api_client.get("/api/v1/ledger/journal?year=2026&month=13").status_code == 400


def test_journal_accrual_basis(api_client, tenant):
    api_client.put(
        "/api/v1/profile",
        {"seller_name": "Tomas IV", "accounting_basis": "accrual"},
        content_type="application/json",
    )
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    make_invoice_paid(api_client, cid)

    jan = api_client.get("/api/v1/ledger/journal?year=2026&month=1").json()
    assert jan["income_total"] == "500.00"  # kaupimo principas – pagal išrašymo datą


def test_journal_expenses_and_summary(api_client):
    post_json(
        api_client,
        "/api/v1/ledger/entries",
        {
            "kind": "expense",
            "document_date": "2026-02-10",
            "counterparty": "Tiekėjas",
            "amount_original": "120.00",
            "deductible": True,
        },
    )
    post_json(
        api_client,
        "/api/v1/ledger/entries",
        {
            "kind": "expense",
            "document_date": "2026-02-11",
            "amount_original": "50.00",
            "deductible": False,
        },
    )
    feb = api_client.get("/api/v1/ledger/journal?year=2026&month=2").json()
    assert feb["expense_total"] == "170.00"
    assert feb["deductible_total"] == "120.00"
    assert feb["net"] == "-120.00"


def test_categories(api_client):
    resp = post_json(
        api_client,
        "/api/v1/ledger/categories",
        {"kind": "expense", "name": "Biuro išlaidos"},
    )
    assert resp.status_code == 201
    cats = api_client.get("/api/v1/ledger/categories?kind=expense").json()
    assert cats[0]["name"] == "Biuro išlaidos"
