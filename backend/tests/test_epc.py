from datetime import date
from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from apps.invoicing.epc import payment_details_text, payment_qr, valid_iban
from apps.invoicing.models import Counterparty, Invoice, InvoiceLine
from apps.invoicing.services import issue_invoice
from apps.mailer.models import EmailOutbox
from apps.mailer.services import queue_invoice_email

from .conftest import post_json

pytestmark = pytest.mark.django_db

IBAN = "LT121000011101001000"


@pytest.fixture
def invoice(tenant):
    tenant.profile.iban = "lt12 1000 0111 0100 1000"
    tenant.profile.save()
    client = Counterparty.objects.create(tenant=tenant, name="UAB Klientas")
    inv = Invoice.objects.create(tenant=tenant, client=client)
    InvoiceLine.objects.create(
        invoice=inv, description="Darbai", quantity=1, unit_price=Decimal("100")
    )
    inv.recalc_total()
    inv.save(update_fields=["total"])
    issue_invoice(inv, date(2026, 1, 10))
    return inv


def test_valid_iban():
    assert valid_iban(IBAN)
    assert not valid_iban("LT121000011101001001")
    assert not valid_iban("LT001")


def test_payload_follows_epc069_12(invoice):
    qr = payment_qr(invoice)
    assert qr is not None
    assert qr.payload.split("\n") == [
        "BCD",
        "002",
        "1",
        "SCT",
        "",
        "Tomas IV",
        IBAN,
        "EUR100.00",
        "",
        "",
        "SF-2026-0001",
    ]
    assert qr.svg_data_uri.startswith("data:image/svg+xml")


def test_amount_is_remaining_balance(api_client, invoice):
    r = post_json(
        api_client,
        f"/api/v1/invoices/{invoice.id}/payments",
        {"amount": "40.00", "paid_at": "2026-01-15"},
    )
    assert r.status_code == 201, r.json()
    invoice.refresh_from_db()
    assert payment_qr(invoice).amount == Decimal("60.00")


def test_no_qr_when_not_payable(invoice):
    invoice.currency = "PLN"
    assert payment_qr(invoice) is None
    invoice.currency = "EUR"
    invoice.status = Invoice.Status.PAID
    assert payment_qr(invoice) is None
    invoice.status = Invoice.Status.DRAFT
    assert payment_qr(invoice) is None
    invoice.status = Invoice.Status.ISSUED
    invoice.tenant.profile.iban = "LT001"
    assert payment_qr(invoice) is None


def test_pdf_template_contains_qr(invoice):
    qr = payment_qr(invoice)
    html = render_to_string(
        "invoicing/invoice_pdf.html",
        {
            "invoice": invoice,
            "profile": invoice.tenant.profile,
            "cash_docs": [],
            "payment_qr": qr,
            "payment_iban": "LT12 1000 0111 0100 1000",
        },
    )
    assert 'src="data:image/svg+xml' in html
    assert "Mokėjimo paskirtis: SF-2026-0001" in html


def test_default_email_body_has_payment_details(invoice, monkeypatch):
    monkeypatch.setattr("apps.invoicing.services.generate_invoice_pdf", lambda inv: b"%PDF-1.4")
    monkeypatch.setattr("apps.mailer.services.queue_email", lambda outbox: None)
    queue_invoice_email(invoice, "k@x.lt")
    body = EmailOutbox.objects.get().body
    assert "IBAN: LT12 1000 0111 0100 1000" in body
    assert "Mokėjimo paskirtis: SF-2026-0001" in body
    assert body == body.strip()


def test_custom_email_body_untouched(invoice, monkeypatch):
    monkeypatch.setattr("apps.invoicing.services.generate_invoice_pdf", lambda inv: b"%PDF-1.4")
    monkeypatch.setattr("apps.mailer.services.queue_email", lambda outbox: None)
    queue_invoice_email(invoice, "k@x.lt", body="Mano tekstas")
    assert EmailOutbox.objects.get().body == "Mano tekstas"
    assert payment_details_text(invoice)
