from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.invoicing.models import Counterparty, Invoice, InvoiceLine
from apps.invoicing.services import issue_invoice
from apps.ledger.models import Category, LedgerEntry
from apps.payments.models import MoneyTransfer
from apps.tenancy.models import TenantMembership

from .conftest import post_json
from .test_camt import OWN, document, ntry, statement

pytestmark = pytest.mark.django_db


def make_invoice(tenant, client, price, day=2):
    inv = Invoice.objects.create(tenant=tenant, client=client)
    InvoiceLine.objects.create(invoice=inv, description="D", quantity=1, unit_price=price)
    inv.recalc_total()
    inv.save(update_fields=["total"])
    issue_invoice(inv, date(2026, 1, day))
    return inv


def upload(api_client, xml):
    f = SimpleUploadedFile("i.xml", xml, content_type="application/xml")
    r = api_client.post("/api/v1/transfers/import", {"file": f, "commit": "true"})
    assert r.status_code == 200, r.content
    return r.json()


def transfer(tenant, **kw):
    values = {"direction": "in", "date": date(2026, 1, 10), "amount": Decimal("100.00")}
    values.update(kw)
    return MoneyTransfer.objects.create(tenant=tenant, source="import", **values)


def test_import_auto_allocates_by_invoice_number(api_client, tenant):
    client = Counterparty.objects.create(tenant=tenant, name="UAB Klientas")
    a = make_invoice(tenant, client, 100)
    b = make_invoice(tenant, client, 80)
    xml = document(
        statement(
            OWN,
            [
                ntry("CRDT", "100.00", 5, "A1", party="Kitas", text=f"Apmokejimas {a.full_number}"),
                # numeris yra, bet suma nesutampa – tik pasiūlymas
                ntry("CRDT", "50.00", 6, "A2", party="Kitas", text=f"sf {b.full_number.lower()}"),
            ],
        )
    )
    body = upload(api_client, xml)
    assert body["auto_allocated_count"] == 1
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == Invoice.Status.PAID and b.status == Invoice.Status.ISSUED
    t = MoneyTransfer.objects.get(external_id="A1|TA1")
    assert t.counterparty_id == client.id  # priskirtas pagal dokumentą

    sug = {s["transfer_id"]: s for s in api_client.get("/api/v1/transfers/suggestions").json()}
    t2 = MoneyTransfer.objects.get(external_id="A2|TA2")
    docs = sug[t2.id]["documents"]
    assert docs[0]["id"] == b.id and "numeris paskirtyje" in docs[0]["reasons"]
    assert docs[0]["auto"] is False
    assert t.id not in sug  # sudengtas – pasiūlymų nėra


def test_suggestion_by_amount_and_name_and_iban_memory(api_client, tenant):
    client = Counterparty.objects.create(tenant=tenant, name="UAB Saulė")
    inv = make_invoice(tenant, client, 42)
    t = transfer(
        tenant,
        amount=Decimal("42.00"),
        counterparty_name="SAULĖ UAB",
        counterparty_iban="LT121000011101001000",
        reference="uz prekes",
    )
    sug = api_client.get("/api/v1/transfers/suggestions").json()
    doc = sug[0]["documents"][0]
    assert doc["id"] == inv.id and {"suma = likutis", "pavadinimas"} <= set(doc["reasons"])
    r = post_json(
        api_client, f"/api/v1/transfers/{t.id}/allocations", {"invoice_id": inv.id, "amount": "42"}
    )
    assert r.status_code == 201
    client.refresh_from_db()
    t.refresh_from_db()
    assert client.iban == "LT121000011101001000" and t.counterparty_id == client.id

    # Kitas importas: kontragentas atpažįstamas pagal įsimintą IBAN.
    xml = document(
        statement(
            OWN, [ntry("CRDT", "10", 9, "Z1", party="Kitoks vardas", iban="LT121000011101001000")]
        )
    )
    upload(api_client, xml)
    assert MoneyTransfer.objects.get(external_id="Z1|TZ1").counterparty_id == client.id


def test_ledger_hint_and_creation_for_tax_and_fee(api_client, tenant):
    fee_cat = Category.objects.create(tenant=tenant, kind="expense", name="Banko mokesčiai")
    vmi = transfer(
        tenant,
        direction="out",
        amount=Decimal("77.00"),
        counterparty_name="VMI, Valstybinė mokesčių inspekcija",
        reference="1311",
    )
    sodra = transfer(
        tenant,
        direction="out",
        amount=Decimal("120.00"),
        counterparty_name="Sodra",
        reference="PSD imoka",
    )
    fee = transfer(
        tenant,
        direction="out",
        amount=Decimal("0.05"),
        bank_code="PMNT/MDOP/NTAV",
        reference="COMMISSION FOR MULTILINK PAYMENTS",
    )
    hints = {
        s["transfer_id"]: s["ledger"]
        for s in api_client.get("/api/v1/transfers/suggestions").json()
    }
    assert hints[vmi.id]["tax_kind"] == "gpm" and hints[vmi.id]["tax_year"] == 2025
    assert hints[sodra.id]["tax_kind"] == "psd" and hints[sodra.id]["tax_year"] == 2026
    assert hints[fee.id]["category_id"] == fee_cat.id and hints[fee.id]["tax_kind"] == ""

    r = post_json(
        api_client,
        f"/api/v1/transfers/{vmi.id}/ledger",
        {"kind": "expense", "tax_kind": "gpm", "tax_year": 2025},
    )
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["status"] == "allocated" and body["ledger_entry_id"]
    entry = LedgerEntry.objects.get(id=body["ledger_entry_id"])
    assert (entry.amount_eur, entry.tax_kind, entry.tax_year, entry.deductible) == (
        Decimal("77.00"),
        "gpm",
        2025,
        False,
    )
    assert entry.paid_date == date(2026, 1, 10)
    # Antrą kartą ir sudengti nebegalima.
    assert (
        post_json(api_client, f"/api/v1/transfers/{vmi.id}/ledger", {"kind": "expense"}).status_code
        == 400
    )
    # Kryptis turi sutapti.
    assert (
        post_json(api_client, f"/api/v1/transfers/{fee.id}/ledger", {"kind": "income"}).status_code
        == 400
    )

    r = api_client.delete(f"/api/v1/transfers/{vmi.id}/ledger")
    assert r.status_code == 200 and r.json()["status"] == "unallocated"
    assert not LedgerEntry.objects.filter(id=entry.id).exists()


def test_ledger_rejects_allocated_or_ignored(api_client, tenant):
    client = Counterparty.objects.create(tenant=tenant, name="K")
    inv = make_invoice(tenant, client, 50)
    t = transfer(tenant, amount=Decimal("50.00"))
    post_json(
        api_client, f"/api/v1/transfers/{t.id}/allocations", {"invoice_id": inv.id, "amount": "50"}
    )
    assert (
        post_json(api_client, f"/api/v1/transfers/{t.id}/ledger", {"kind": "income"}).status_code
        == 400
    )
    ign = transfer(tenant, ignored=True)
    assert (
        post_json(api_client, f"/api/v1/transfers/{ign.id}/ledger", {"kind": "income"}).status_code
        == 400
    )


def test_ledger_tenant_isolation_and_accountant(api_client, user, tenant, other_tenant):
    other = transfer(other_tenant, direction="out")
    assert (
        post_json(
            api_client, f"/api/v1/transfers/{other.id}/ledger", {"kind": "expense"}
        ).status_code
        == 404
    )
    own = transfer(tenant, direction="out")
    TenantMembership.objects.filter(user=user, tenant=tenant).update(role="accountant")
    assert (
        post_json(api_client, f"/api/v1/transfers/{own.id}/ledger", {"kind": "expense"}).status_code
        == 403
    )
    assert api_client.get("/api/v1/transfers/suggestions").status_code == 200


def test_number_match_needs_word_boundary():
    from apps.payments.matching import number_in_text

    assert number_in_text("SF20260001", "apmokejimas sf-2026/0001.")
    assert not number_in_text("1234", "Saskaita 12345")
    assert not number_in_text("SF20260001", "SF-2026-00012")


def test_pln_ledger_requires_rate(api_client, tenant):
    t = transfer(tenant, direction="out", currency="PLN", amount=Decimal("400.00"))
    url = f"/api/v1/transfers/{t.id}/ledger"
    assert post_json(api_client, url, {"kind": "expense"}).status_code == 400
    r = post_json(api_client, url, {"kind": "expense", "exchange_rate": "0.235"})
    assert r.status_code == 201, r.content
    assert LedgerEntry.objects.get(id=r.json()["ledger_entry_id"]).amount_eur == Decimal("94.00")


def test_transfer_edit_updates_ledger_entry(api_client, tenant):
    r = post_json(api_client, "/api/v1/transfers",
                  {"direction": "out", "date": "2026-02-01", "amount": "10.00"})
    tid = r.json()["id"]
    r = post_json(api_client, f"/api/v1/transfers/{tid}/ledger", {"kind": "expense"})
    entry_id = r.json()["ledger_entry_id"]
    r = api_client.put(f"/api/v1/transfers/{tid}", {"date": "2026-02-03", "amount": "12.50"},
                       content_type="application/json")
    assert r.status_code == 200, r.content
    entry = LedgerEntry.objects.get(id=entry_id)
    assert (entry.amount_eur, entry.paid_date) == (Decimal("12.50"), date(2026, 2, 3))
