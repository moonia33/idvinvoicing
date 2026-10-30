from datetime import date
from decimal import Decimal

import pytest

from apps.core.ltnum import lt_amount_words, lt_int_words
from apps.invoicing.models import Client, Invoice, InvoiceLine, Payment
from apps.invoicing.services import issue_invoice

from .conftest import post_json

pytestmark = pytest.mark.django_db


@pytest.fixture
def issued_invoice(tenant):
    client = Client.objects.create(tenant=tenant, name="UAB Klientas")
    inv = Invoice.objects.create(tenant=tenant, client=client)
    InvoiceLine.objects.create(
        invoice=inv, description="Konsultacija", quantity=1, unit_price=Decimal("100")
    )
    issue_invoice(inv, date(2026, 1, 10))
    return inv


def pay(api_client, inv, **kwargs):
    body = {"amount": "100.00", "paid_at": "2026-01-15"}
    body.update(kwargs)
    return post_json(api_client, f"/api/v1/invoices/{inv.id}/payments", body)


def test_cash_payment_auto_kpo_number(api_client, issued_invoice):
    r = pay(api_client, issued_invoice, method="cash", doc_type="kpo")
    assert r.status_code == 201, r.json()
    assert r.json()["doc_number"] == "KPO-2026-0001"

    inv2 = Invoice.objects.create(tenant=issued_invoice.tenant, client=issued_invoice.client)
    InvoiceLine.objects.create(invoice=inv2, description="x", quantity=1, unit_price=Decimal("5"))
    issue_invoice(inv2, date(2026, 1, 20))
    r = pay(api_client, inv2, amount="5.00", method="cash", doc_type="kpo")
    assert r.json()["doc_number"] == "KPO-2026-0002"


def test_ppk_separate_sequence(api_client, issued_invoice):
    r = pay(api_client, issued_invoice, method="cash", doc_type="ppk")
    assert r.json()["doc_number"] == "PPK-2026-0001"


def test_manual_doc_number_preserved(api_client, issued_invoice):
    r = pay(api_client, issued_invoice, method="bank", doc_number="OP-998877")
    assert r.status_code == 201
    assert r.json()["doc_number"] == "OP-998877"


def test_cash_doc_pdf_endpoint(api_client, issued_invoice, monkeypatch):
    monkeypatch.setattr("apps.invoicing.api.generate_cash_doc_pdf", lambda p: b"%PDF-cash")
    pay(api_client, issued_invoice, method="cash", doc_type="kpo")
    payment = Payment.objects.get(invoice=issued_invoice)
    r = api_client.get(f"/api/v1/payments/{payment.id}/cash-doc.pdf")
    assert r.status_code == 200
    assert r.content == b"%PDF-cash"
    assert "KPO-2026-0001" in r["Content-Disposition"]


def test_cash_doc_pdf_rejects_plain_payment(api_client, issued_invoice):
    pay(api_client, issued_invoice, method="bank")
    payment = Payment.objects.get(invoice=issued_invoice)
    r = api_client.get(f"/api/v1/payments/{payment.id}/cash-doc.pdf")
    assert r.status_code == 400


def test_invoice_pdf_with_cash_docs_flag(api_client, issued_invoice, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.invoicing.api.generate_invoice_pdf",
        lambda inv, with_cash_docs=False: calls.append(with_cash_docs) or b"%PDF",
    )
    api_client.get(f"/api/v1/invoices/{issued_invoice.id}/pdf?with_cash_docs=true")
    assert calls == [True]


# --- ltnum ---


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "nulis"),
        (1, "vienas"),
        (10, "dešimt"),
        (11, "vienuolika"),
        (21, "dvidešimt vienas"),
        (100, "šimtas"),
        (115, "šimtas penkiolika"),
        (999, "devyni šimtai devyniasdešimt devyni"),
        (1000, "vienas tūkstantis"),
        (2000, "du tūkstančiai"),
        (11000, "vienuolika tūkstančių"),
        (21000, "dvidešimt vienas tūkstantis"),
        (25000, "dvidešimt penki tūkstančiai"),
        (100000, "šimtas tūkstančių"),
    ],
)
def test_lt_int_words(n, expected):
    assert lt_int_words(n) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("0"), "Nulis Eur 00 ct"),
        (Decimal("0.99"), "Nulis Eur 99 ct"),
        (Decimal("21"), "Dvidešimt vienas Eur 00 ct"),
        (Decimal("1234.56"), "Vienas tūkstantis du šimtai trisdešimt keturi Eur 56 ct"),
    ],
)
def test_lt_amount_words(amount, expected):
    assert lt_amount_words(amount) == expected
