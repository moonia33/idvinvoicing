import importlib
from datetime import date
from decimal import Decimal

import pytest
from django.apps import apps as django_apps

from apps.invoicing.models import Counterparty, Invoice, InvoiceLine, Payment
from apps.invoicing.services import issue_invoice
from apps.payments.models import MoneyTransfer
from apps.purchases.models import Purchase, PurchasePayment
from apps.tenancy.models import TenantMembership

from .conftest import post_json

pytestmark = pytest.mark.django_db
URL = "/api/v1/transfers"


@pytest.fixture
def klientas(tenant):
    return Counterparty.objects.create(tenant=tenant, name="UAB Klientas")


def make_invoice(tenant, client, price, day):
    inv = Invoice.objects.create(tenant=tenant, client=client)
    InvoiceLine.objects.create(invoice=inv, description="Darbas", quantity=1, unit_price=price)
    inv.recalc_total()
    inv.save(update_fields=["total"])
    issue_invoice(inv, date(2026, 1, day))
    return inv


def make_purchase(api_client, supplier_id, price, currency="EUR", rate="1"):
    r = post_json(
        api_client,
        "/api/v1/purchases",
        {
            "supplier_id": supplier_id,
            "doc_number": f"P-{price}",
            "document_date": "2026-01-05",
            "currency": currency,
            "exchange_rate": rate,
            "lines": [{"description": "Prekė", "quantity": "1", "unit_price": price}],
        },
    )
    assert r.status_code == 201, r.content
    return Purchase.objects.get(id=r.json()["id"])


def new_transfer(api_client, **kwargs):
    body = {"direction": "in", "date": "2026-02-01", "amount": "150.00"}
    body.update(kwargs)
    return post_json(api_client, URL, body)


def test_one_payment_covers_two_invoices(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    b = make_invoice(tenant, klientas, Decimal("80"), 12)
    r = new_transfer(
        api_client,
        counterparty_id=klientas.id,
        allocations=[
            {"invoice_id": a.id, "amount": "100.00"},
            {"invoice_id": b.id, "amount": "50.00"},
        ],
    )
    assert r.status_code == 201, r.content
    data = r.json()
    assert data["status"] == "allocated" and data["unallocated"] == "0.00"
    assert len(data["allocations"]) == 2
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == Invoice.Status.PAID
    assert b.status == Invoice.Status.PARTIALLY_PAID
    # pinigų principas: sudengimo data = mokėjimo data
    assert set(Payment.objects.values_list("paid_at", flat=True)) == {date(2026, 2, 1)}

    docs = api_client.get(f"{URL}/open-documents?direction=in&counterparty_id={klientas.id}")
    assert [(d["id"], d["remaining"]) for d in docs.json()] == [(b.id, "30.00")]


def test_overpayment_stays_unallocated(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(
        api_client, amount="120.00", allocations=[{"invoice_id": a.id, "amount": "100"}]
    )
    assert r.status_code == 201
    assert r.json()["status"] == "partial" and r.json()["unallocated"] == "20.00"
    assert api_client.get(f"{URL}?status=open").json()[0]["id"] == r.json()["id"]


def test_allocation_limits(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(api_client, amount="50.00", allocations=[{"invoice_id": a.id, "amount": "60"}])
    assert r.status_code == 400
    r = new_transfer(
        api_client, amount="500.00", allocations=[{"invoice_id": a.id, "amount": "101"}]
    )
    assert r.status_code == 400
    assert MoneyTransfer.objects.count() == 0  # atomic


def test_direction_mismatch(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(
        api_client, direction="out", allocations=[{"invoice_id": a.id, "amount": "10"}]
    )
    assert r.status_code == 400


def test_other_tenant_document_rejected(api_client, other_tenant):
    cp = Counterparty.objects.create(tenant=other_tenant, name="Svetimas")
    inv = make_invoice(other_tenant, cp, Decimal("100"), 10)
    r = new_transfer(api_client, allocations=[{"invoice_id": inv.id, "amount": "10"}])
    assert r.status_code == 404
    r = new_transfer(api_client, counterparty_id=cp.id)
    assert r.status_code == 404


def test_ignored_personal_transfer(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(api_client, ignored=True, counterparty_name="Asmeninis pervedimas")
    assert r.status_code == 201 and r.json()["status"] == "ignored"
    tid = r.json()["id"]
    r = post_json(api_client, f"{URL}/{tid}/allocations", {"invoice_id": a.id, "amount": "10"})
    assert r.status_code == 400
    assert api_client.get(f"{URL}?status=ignored").json()[0]["id"] == tid


def test_allocate_later_and_unallocate(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    tid = new_transfer(api_client, amount="100.00").json()["id"]
    r = post_json(api_client, f"{URL}/{tid}/allocations", {"invoice_id": a.id, "amount": "100"})
    assert r.status_code == 201 and r.json()["status"] == "allocated"
    a.refresh_from_db()
    assert a.status == Invoice.Status.PAID
    alloc = r.json()["allocations"][0]
    r = api_client.delete(f"{URL}/{tid}/allocations/invoice/{alloc['id']}")
    assert r.status_code == 200 and r.json()["status"] == "unallocated"
    a.refresh_from_db()
    assert a.status == Invoice.Status.ISSUED


def test_update_date_resyncs_allocations(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    tid = new_transfer(api_client, allocations=[{"invoice_id": a.id, "amount": "100"}]).json()["id"]
    r = api_client.put(
        f"{URL}/{tid}",
        {"date": "2026-03-03", "amount": "150.00", "method": "cash"},
        content_type="application/json",
    )
    assert r.status_code == 200, r.content
    p = Payment.objects.get()
    assert p.paid_at == date(2026, 3, 3) and p.method == "cash"
    r = api_client.put(
        f"{URL}/{tid}", {"date": "2026-03-03", "amount": "90.00"}, content_type="application/json"
    )
    assert r.status_code == 400


def test_delete_transfer_resets_documents(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    tid = new_transfer(api_client, allocations=[{"invoice_id": a.id, "amount": "100"}]).json()["id"]
    assert api_client.delete(f"{URL}/{tid}").status_code == 204
    a.refresh_from_db()
    assert a.status == Invoice.Status.ISSUED and not Payment.objects.exists()


def test_invoice_page_payment_mirrors_transfer(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = post_json(
        api_client, f"/api/v1/invoices/{a.id}/payments", {"amount": "40", "paid_at": "2026-01-20"}
    )
    assert r.status_code == 201
    t = MoneyTransfer.objects.get()
    assert (t.direction, t.amount, t.counterparty_id, t.status) == (
        "in",
        Decimal("40"),
        klientas.id,
        "allocated",
    )
    api_client.put(
        f"/api/v1/payments/{r.json()['id']}",
        {"amount": "60", "paid_at": "2026-01-21"},
        content_type="application/json",
    )
    t.refresh_from_db()
    assert t.amount == Decimal("60") and t.date == date(2026, 1, 21)
    api_client.delete(f"/api/v1/payments/{r.json()['id']}")
    assert not MoneyTransfer.objects.exists()


def test_cancel_invoice_removes_manual_keeps_imported(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    imported = MoneyTransfer.objects.create(
        tenant=tenant, direction="in", date=date(2026, 2, 1), amount=Decimal("30"), source="import"
    )
    post_json(api_client, f"{URL}/{imported.id}/allocations", {"invoice_id": a.id, "amount": "30"})
    post_json(
        api_client, f"/api/v1/invoices/{a.id}/payments", {"amount": "20", "paid_at": "2026-01-20"}
    )
    assert post_json(api_client, f"/api/v1/invoices/{a.id}/cancel", {}).status_code == 200
    assert list(MoneyTransfer.objects.values_list("id", flat=True)) == [imported.id]


def test_cancel_invoice_keeps_register_payment(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(api_client, amount="30.00", allocations=[{"invoice_id": a.id, "amount": "30"}])
    assert post_json(api_client, f"/api/v1/invoices/{a.id}/cancel", {}).status_code == 200
    assert MoneyTransfer.objects.get(id=r.json()["id"]).status == "unallocated"


def test_purchase_allocation_and_pln(api_client, tenant):
    sup = Counterparty.objects.create(tenant=tenant, name="Tiekėjas", is_supplier=True)
    eur = make_purchase(api_client, sup.id, "50.00")
    pln = make_purchase(api_client, sup.id, "400.00", currency="PLN", rate="0.25")
    r = new_transfer(
        api_client,
        direction="out",
        amount="150.00",
        counterparty_id=sup.id,
        allocations=[
            {"purchase_id": eur.id, "amount": "50"},
            {"purchase_id": pln.id, "amount": "100", "exchange_rate": "0.25"},
        ],
    )
    assert r.status_code == 201, r.content
    assert r.json()["status"] == "allocated"
    pp = PurchasePayment.objects.get(purchase=pln)
    assert pp.amount_original == Decimal("400.00") and pp.amount_eur == Decimal("100.00")
    pln.refresh_from_db()
    assert pln.status == Purchase.Status.PAID


def test_accountant_read_only(api_client, tenant, user):
    TenantMembership.objects.filter(user=user).update(role=TenantMembership.Role.ACCOUNTANT)
    assert api_client.get(URL).status_code == 200
    assert new_transfer(api_client).status_code == 403


def test_list_filters(api_client, tenant, klientas):
    new_transfer(api_client, counterparty_id=klientas.id, date="2026-01-01")
    new_transfer(api_client, direction="out", counterparty_name="Sodra", reference="VSD")
    assert len(api_client.get(f"{URL}?direction=out").json()) == 1
    assert len(api_client.get(f"{URL}?q=sodra").json()) == 1
    assert len(api_client.get(f"{URL}?date_from=2026-01-15").json()) == 1
    assert (
        api_client.get(f"{URL}?counterparty_id={klientas.id}").json()[0]["counterparty_display"]
        == "UAB Klientas"
    )


def test_data_migration_creates_transfers(tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    Payment.objects.create(invoice=a, amount=Decimal("100"), paid_at=date(2026, 1, 15))
    mig = importlib.import_module("apps.payments.migrations.0002_transfers_from_payments")
    mig.forwards(django_apps, None)
    t = MoneyTransfer.objects.get()
    assert t.amount == Decimal("100") and t.status == "allocated" and t.counterparty == klientas


def test_document_edit_of_register_payment(api_client, tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    r = new_transfer(
        api_client, amount="150.00", allocations=[{"invoice_id": a.id, "amount": "100"}]
    )
    tid, pid = r.json()["id"], r.json()["allocations"][0]["id"]

    def put(body):
        return api_client.put(f"/api/v1/payments/{pid}", body, content_type="application/json")

    assert put({"amount": "90", "paid_at": "2026-02-01"}).status_code == 200
    t = MoneyTransfer.objects.get(id=tid)
    assert t.amount == Decimal("150.00") and t.unallocated == Decimal("60.00")
    assert put({"amount": "90", "paid_at": "2026-02-05"}).status_code == 400
    api_client.delete(f"/api/v1/payments/{pid}")
    assert MoneyTransfer.objects.filter(id=tid).exists()


def test_zero_paid_now_purchase_has_no_transfer(api_client, tenant):
    sup = Counterparty.objects.create(tenant=tenant, name="Tiekėjas", is_supplier=True)
    r = post_json(
        api_client,
        "/api/v1/purchases",
        {
            "supplier_id": sup.id,
            "document_date": "2026-01-05",
            "paid_now": True,
            "lines": [{"description": "Nemokama", "quantity": "1", "unit_price": "0"}],
        },
    )
    assert r.status_code == 201, r.content
    assert not MoneyTransfer.objects.exists()


def test_data_migration_backwards_keeps_payments(tenant, klientas):
    a = make_invoice(tenant, klientas, Decimal("100"), 10)
    kept = Payment.objects.create(invoice=a, amount=Decimal("100"), paid_at=date(2026, 1, 15))
    Payment.objects.create(invoice=a, amount=Decimal("0"), paid_at=date(2026, 1, 16))
    mig = importlib.import_module("apps.payments.migrations.0002_transfers_from_payments")
    mig.forwards(django_apps, None)
    assert MoneyTransfer.objects.count() == 1 and MoneyTransfer.objects.get().mirror
    mig.backwards(django_apps, None)
    assert Payment.objects.count() == 2 and Payment.objects.get(id=kept.id).transfer is None
