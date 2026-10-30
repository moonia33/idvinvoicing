from datetime import date, timedelta

import pytest

from apps.invoicing.models import Invoice, RecurringTemplate
from apps.invoicing.services import add_months
from apps.invoicing.tasks import generate_recurring_invoices
from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def test_add_months_edges():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 12, 15), 1) == date(2027, 1, 15)
    assert add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)


def test_recurring_generates_invoice(api_client, tenant, monkeypatch):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    resp = post_json(
        api_client,
        "/api/v1/recurring",
        {
            "client_id": cid,
            "frequency": "monthly",
            "next_run_date": str(date.today()),
            "lines": [{"description": "Abonementas", "unit_price": "99.00"}],
        },
    )
    assert resp.status_code == 201

    result = generate_recurring_invoices()
    assert result["created"] == 1
    inv = Invoice.objects.get()
    assert inv.status == "issued"
    assert inv.full_number.startswith("SF-")
    assert str(inv.total) == "99.00"

    tpl = RecurringTemplate.objects.get()
    assert tpl.next_run_date > date.today()


def test_recurring_auto_send(api_client, tenant, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "apps.invoicing.tasks.queue_invoice_email", lambda inv, to: sent.append(to)
    )
    cid = post_json(
        api_client, "/api/v1/clients", {"name": "K", "email": "k@x.lt"}
    ).json()["id"]
    post_json(
        api_client,
        "/api/v1/recurring",
        {
            "client_id": cid,
            "frequency": "monthly",
            "next_run_date": str(date.today() - timedelta(days=1)),
            "auto_send": True,
            "lines": [{"description": "Abonementas", "unit_price": "10.00"}],
        },
    )
    result = generate_recurring_invoices()
    assert result["queued_emails"] == 1
    assert sent == ["k@x.lt"]


def test_recurring_future_not_generated(api_client):
    cid = post_json(api_client, "/api/v1/clients", {"name": "K"}).json()["id"]
    post_json(
        api_client,
        "/api/v1/recurring",
        {
            "client_id": cid,
            "frequency": "yearly",
            "next_run_date": str(date.today() + timedelta(days=30)),
            "lines": [{"description": "x", "unit_price": "10.00"}],
        },
    )
    assert generate_recurring_invoices()["created"] == 0
