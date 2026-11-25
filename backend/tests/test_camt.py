from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.invoicing.models import Counterparty, Invoice, InvoiceLine
from apps.invoicing.services import issue_invoice
from apps.payments import camt
from apps.payments.models import BankImport, MoneyTransfer
from apps.tenancy.models import TenantMembership

from .conftest import post_json

pytestmark = pytest.mark.django_db
URL = "/api/v1/transfers/import"
NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"
OWN = "LT117290099000000001"
OTHER_OWN = "LT137290099000000002"


def ntry(ind, amount, day, ref, *, party="", iban="", code="", text="", fmly="RCDT", sts="BOOK"):
    role = "Dbtr" if ind == "CRDT" else "Cdtr"
    pid = f"<Id><OrgId><Othr><Id>{code}</Id></Othr></OrgId></Id>" if code else ""
    acct = f"<{role}Acct><Id><IBAN>{iban}</IBAN></Id></{role}Acct>" if iban else ""
    return (
        f'<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts>{sts}</Sts>'
        f"<BookgDt><Dt>2026-01-{day:02d}</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef>"
        f"<BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>{fmly}</Cd><SubFmlyCd>OTHR</SubFmlyCd></Fmly>"
        f"</Domn></BkTxCd><NtryDtls><TxDtls><Refs><TxId>T{ref}</TxId></Refs><RltdPties>"
        f"<{role}><Nm>{party}</Nm>{pid}</{role}>{acct}</RltdPties>"
        f"<RmtInf><Ustrd>{text}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"
    )


def statement(iban, entries, ccy="EUR"):
    return (
        f"<Stmt><Id>S-{iban}</Id><FrToDt><FrDtTm>2026-01-01T00:00:00</FrDtTm>"
        f"<ToDtTm>2026-01-31T23:59:59</ToDtTm></FrToDt><Acct><Id><IBAN>{iban}</IBAN></Id>"
        f"<Ccy>{ccy}</Ccy><Ownr><Nm>Mano veikla</Nm><Id><OrgId><Othr><Id>300000001</Id>"
        f"</Othr></OrgId></Id></Ownr><Svcr><FinInstnId><Nm>Testo bankas</Nm></FinInstnId>"
        f"</Svcr></Acct>{''.join(entries)}</Stmt>"
    )


def document(*stmts):
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><Document xmlns="{NS}"><BkToCstmrStmt>'
        f"<GrpHdr><MsgId>1</MsgId></GrpHdr>{''.join(stmts)}</BkToCstmrStmt></Document>"
    ).encode()


SAMPLE = document(
    statement(
        OWN,
        [
            ntry(
                "CRDT",
                "100.00",
                3,
                "R1",
                party="UAB KLIENTAS",
                iban="LT987300010000000009",
                text="Apmokejimas SF-2026-0001",
            ),
            ntry("DBIT", "20", 4, "R2", party="Google ADS DUBLIN", fmly="CCRD"),
            ntry(
                "DBIT",
                "50",
                5,
                "R3",
                party="Mano veikla",
                iban=OTHER_OWN,
                text="Mokėjimas į savo sąskaitą",
            ),
            ntry("CRDT", "7.00", 6, "R4", party="Laukia", sts="PDNG"),
            ntry("DBIT", "12.34", 7, "R5", party="Tiekejas", code="123456789"),
        ],
    ),
    statement(OTHER_OWN, [ntry("CRDT", "50", 5, "R3", party="Mano veikla", iban=OWN)]),
)


def upload(api_client, data=SAMPLE, **form):
    f = SimpleUploadedFile("israsas.xml", data, content_type="application/xml")
    return api_client.post(URL, {"file": f, **form})


def test_parse_sample():
    stmts = camt.parse(SAMPLE)
    assert [s.account_iban for s in stmts] == [OWN, OTHER_OWN]
    first = stmts[0]
    assert first.skipped == 1 and len(first.entries) == 4
    e = first.entries[0]
    assert (e.direction, e.amount, e.date) == ("in", Decimal("100.00"), date(2026, 1, 3))
    assert e.counterparty_iban == "LT987300010000000009" and "SF-2026-0001" in e.reference
    assert e.external_id == "R1|TR1"
    assert first.entries[1].method == "card"
    assert first.period_from == date(2026, 1, 1)


def test_parse_paysera_datetime_and_forx():
    xml = document(
        statement(OWN, [ntry("DBIT", "10", 2, "P1", party="Paysera LT")])
        .replace(
            "<BookgDt><Dt>2026-01-02</Dt></BookgDt>",
            "<BookgDt><DtTm>2026-01-02T18:05:06+02:00</DtTm></BookgDt>",
        )
        .replace("<Cd>PMNT</Cd>", "<Cd>FORX</Cd>")
    )
    e = camt.parse(xml)[0].entries[0]
    assert e.date == date(2026, 1, 2) and e.own_transfer


@pytest.mark.parametrize(
    "data",
    [
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">&x;</Document>',
        b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.03'/>",
        b"ne xml",
    ],
)
def test_rejects_unsafe_or_foreign_xml(api_client, data):
    r = upload(api_client, data)
    assert r.status_code == 400
    assert not MoneyTransfer.objects.exists()


def test_rejects_large_file(monkeypatch):
    monkeypatch.setattr(camt, "MAX_FILE_SIZE", 100)
    with pytest.raises(camt.CamtError):
        camt.parse(SAMPLE)


def test_preview_does_not_write(api_client, tenant):
    Counterparty.objects.create(tenant=tenant, name="UAB Klientas")
    sup = Counterparty.objects.create(tenant=tenant, name="X", code="123456789")
    r = upload(api_client)
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["new_count"] == 5 and body["duplicate_count"] == 0
    rows = {row["external_id"]: row for row in body["entries"]}
    assert rows["R3|TR3"]["own_transfer"]  # pervedimas tarp savų sąskaitų
    assert rows["R1|TR1"]["counterparty_id"] is not None  # pagal pavadinimą be „UAB“
    assert rows["R5|TR5"]["counterparty_id"] == sup.id  # pagal įmonės kodą
    assert not MoneyTransfer.objects.exists()


def test_commit_then_reimport_is_idempotent(api_client, tenant):
    ignored = f'["{OWN}:R3|TR3", "{OTHER_OWN}:R3|TR3"]'
    r = upload(api_client, commit="true", ignored=ignored)
    assert r.status_code == 200, r.content
    assert r.json()["created_count"] == 5
    qs = MoneyTransfer.objects.filter(tenant=tenant)
    assert qs.count() == 5 and set(qs.values_list("source", flat=True)) == {"import"}
    assert qs.filter(ignored=True).count() == 2
    assert all(t.status in ("unallocated", "ignored") for t in qs)
    assert BankImport.objects.filter(tenant=tenant).count() == 2

    again = upload(api_client, commit="true").json()
    assert again["created_count"] == 0 and again["duplicate_count"] == 5
    assert qs.count() == 5
    assert upload(api_client).json()["new_count"] == 0


def test_import_isolated_per_tenant(api_client, other_tenant):
    MoneyTransfer.objects.create(
        tenant=other_tenant,
        direction="in",
        date=date(2026, 1, 3),
        amount=Decimal("100"),
        source="import",
        account_iban=OWN,
        external_id="R1|TR1",
    )
    assert upload(api_client).json()["duplicate_count"] == 0
    assert upload(api_client, commit="true").json()["created_count"] == 5


def test_imported_transfer_can_be_allocated(api_client, tenant):
    client = Counterparty.objects.create(tenant=tenant, name="UAB Klientas")
    inv = Invoice.objects.create(tenant=tenant, client=client)
    InvoiceLine.objects.create(invoice=inv, description="Darbas", quantity=1, unit_price=100)
    inv.recalc_total()
    inv.save(update_fields=["total"])
    issue_invoice(inv, date(2026, 1, 2))
    upload(api_client, commit="true")
    t = MoneyTransfer.objects.get(external_id="R1|TR1")
    r = post_json(
        api_client, f"/api/v1/transfers/{t.id}/allocations", {"invoice_id": inv.id, "amount": "100"}
    )
    assert r.status_code == 201, r.content
    inv.refresh_from_db()
    assert inv.status == Invoice.Status.PAID
    listed = api_client.get(f"/api/v1/transfers?source=import&bank_import={t.bank_import_id}")
    assert len(listed.json()) == 4


def test_accountant_cannot_import(api_client, user, tenant):
    TenantMembership.objects.filter(user=user, tenant=tenant).update(role="accountant")
    assert upload(api_client, commit="true").status_code == 403
    assert not MoneyTransfer.objects.exists()


def test_cash_documents_on_transfer(api_client, tenant):
    base = {"date": "2026-02-01", "amount": "10.00", "method": "cash"}
    kpo = post_json(api_client, "/api/v1/transfers", {**base, "direction": "in", "doc_type": "kpo"})
    assert kpo.status_code == 201, kpo.content
    assert kpo.json()["doc_number"].startswith("KPO")
    kvitas = post_json(
        api_client,
        "/api/v1/transfers",
        {**base, "direction": "out", "doc_type": "receipt", "doc_number": "K-77"},
    )
    assert kvitas.status_code == 201 and kvitas.json()["doc_number"] == "K-77"
    wrong = post_json(
        api_client, "/api/v1/transfers", {**base, "direction": "out", "doc_type": "kpo"}
    )
    assert wrong.status_code == 400
    card = post_json(
        api_client,
        "/api/v1/transfers",
        {**base, "method": "card", "direction": "in", "doc_type": "receipt"},
    )
    assert card.status_code == 400
    bank = post_json(
        api_client,
        "/api/v1/transfers",
        {**base, "method": "bank", "direction": "in", "doc_number": "PAV-1"},
    )
    assert bank.status_code == 201 and bank.json()["doc_number"] == "PAV-1"
    assert api_client.get("/api/v1/transfers?q=PAV-1").json()[0]["id"] == bank.json()["id"]


def test_cash_document_number_shared_by_allocations(api_client, tenant):
    client = Counterparty.objects.create(tenant=tenant, name="UAB Klientas")
    invs = []
    for price in (30, 20):
        inv = Invoice.objects.create(tenant=tenant, client=client)
        InvoiceLine.objects.create(invoice=inv, description="D", quantity=1, unit_price=price)
        inv.recalc_total()
        inv.save(update_fields=["total"])
        issue_invoice(inv, date(2026, 1, 2))
        invs.append(inv)
    r = post_json(
        api_client,
        "/api/v1/transfers",
        {
            "direction": "in",
            "date": "2026-02-01",
            "amount": "50.00",
            "method": "cash",
            "doc_type": "kpo",
            "allocations": [{"invoice_id": i.id, "amount": str(i.total)} for i in invs],
        },
    )
    assert r.status_code == 201, r.content
    numbers = {a["doc_number"] for a in r.json()["allocations"]}
    assert numbers == {r.json()["doc_number"]}


def test_batch_entry_split_and_reversal():
    tx = (
        '<TxDtls><Refs><TxId>{i}</TxId></Refs><AmtDtls><TxAmt><Amt Ccy="EUR">{a}</Amt></TxAmt>'
        "</AmtDtls><RltdPties><Cdtr><Nm>Gavejas {i}</Nm></Cdtr></RltdPties></TxDtls>"
    )
    batch = (
        '<Ntry><NtryRef>B1</NtryRef><Amt Ccy="EUR">30.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>'
        "<Sts>BOOK</Sts><BookgDt><Dt>2026-01-09</Dt></BookgDt><NtryDtls>"
        + tx.format(i=1, a="10.00")
        + tx.format(i=2, a="20.00")
        + "</NtryDtls></Ntry>"
    )
    reversal = ntry("CRDT", "5", 10, "RV").replace(
        "<CdtDbtInd>CRDT</CdtDbtInd>", "<CdtDbtInd>CRDT</CdtDbtInd><RvslInd>true</RvslInd>"
    )
    entries = camt.parse(document(statement(OWN, [batch, reversal])))[0].entries
    assert [(e.counterparty_name, e.amount) for e in entries[:2]] == [
        ("Gavejas 1", Decimal("10.00")),
        ("Gavejas 2", Decimal("20.00")),
    ]
    assert entries[0].external_id != entries[1].external_id
    assert entries[0].external_id.startswith("B1")
    assert entries[2].direction == "in"


def test_commit_rejected_after_tenant_switch(api_client, tenant):
    r = upload(api_client, commit="true", tenant_id=str(tenant.id + 999))
    assert r.status_code == 409
    assert not MoneyTransfer.objects.exists()
    assert upload(api_client, commit="true", tenant_id=str(tenant.id)).status_code == 200
