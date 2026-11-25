from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from ninja.errors import HttpError

from apps.invoicing.models import Invoice, Payment
from apps.invoicing.services import next_cash_doc_number
from apps.payments.models import MoneyTransfer
from apps.purchases.models import Purchase, PurchasePayment
from apps.purchases.services import next_kio_number

CENT = Decimal("0.01")
OPEN_INVOICE = (Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID)
OPEN_PURCHASE = (Purchase.Status.RECEIVED, Purchase.Status.PARTIALLY_PAID)


def invoice_remaining(invoice: Invoice) -> Decimal:
    return invoice.total - invoice.paid_total


def purchase_remaining(purchase: Purchase) -> Decimal:
    return purchase.total - purchase.paid_total


def transfer_for_invoice_payment(payment: Payment) -> MoneyTransfer | None:
    inv = payment.invoice
    if payment.amount <= 0:
        return None
    return MoneyTransfer.objects.create(
        tenant=inv.tenant,
        direction=MoneyTransfer.Direction.IN,
        date=payment.paid_at,
        amount=payment.amount,
        currency=inv.currency,
        method=payment.method,
        counterparty=inv.client,
        note=payment.note,
        mirror=True,
    )


def transfer_for_purchase_payment(payment: PurchasePayment) -> MoneyTransfer | None:
    pur = payment.purchase
    if payment.amount_original <= 0:
        return None
    return MoneyTransfer.objects.create(
        tenant=pur.tenant,
        direction=MoneyTransfer.Direction.OUT,
        date=payment.paid_at,
        amount=payment.amount_original,
        currency=pur.currency,
        method=payment.method,
        counterparty=pur.supplier,
        note=payment.note,
        mirror=True,
    )


def sync_document_payment(payment) -> None:
    """Dokumento puslapyje redaguotą mokėjimą suderina su registru.

    Iš dokumento sukurtas (mirror) mokėjimas atnaujinamas kartu; registre įvesto
    mokėjimo sudengimo data ir būdas turi sutapti su mokėjimu (pinigų principas)."""
    transfer = payment.transfer
    if transfer is None:
        # Pvz. nulinis mokėjimas pataisytas į teigiamą – dabar jis turi atsirasti registre.
        if isinstance(payment, Payment):
            transfer = transfer_for_invoice_payment(payment)
        else:
            transfer = transfer_for_purchase_payment(payment)
        if transfer is not None:
            payment.transfer = transfer
            payment.save(update_fields=["transfer"])
        return
    amount = transfer.allocation_amount(payment)
    if transfer.mirror:
        if amount <= 0:
            raise HttpError(400, "Suma turi būti teigiama")
        transfer.amount = amount
        transfer.date = payment.paid_at
        transfer.method = payment.method
        transfer.save(update_fields=["amount", "date", "method"])
        return
    if payment.paid_at != transfer.date or payment.method != transfer.method:
        raise HttpError(
            400, "Mokėjimas įvestas registre – datą ir būdą keiskite puslapyje „Mokėjimai“"
        )
    if transfer.unallocated < 0:
        raise HttpError(400, "Sudengta suma viršija mokėjimo sumą")


def mirror_transfer_ids(payments) -> list[int]:
    """Iš dokumento sukurti mokėjimai, kuriuos reikia šalinti kartu su sudengimu."""
    return [p.transfer_id for p in payments if p.transfer_id and p.transfer.mirror]


def delete_mirror_transfers(transfer_ids: Iterable[int]) -> None:
    MoneyTransfer.objects.filter(id__in=set(transfer_ids), mirror=True).delete()


CASH_DOCS = {
    MoneyTransfer.Direction.IN: ("kpo", "ppk", "receipt"),
    MoneyTransfer.Direction.OUT: ("kio", "ppk", "receipt"),
}


def assign_cash_doc(transfer: MoneyTransfer) -> None:
    """Patikrina kasos dokumento tipą ir, jei reikia, suteikia KPO/PPK/KIO numerį."""
    if not transfer.doc_type:
        return
    if transfer.method != MoneyTransfer.Method.CASH:
        raise HttpError(400, "Kasos dokumentas galimas tik grynųjų mokėjimui")
    if transfer.doc_type not in CASH_DOCS[MoneyTransfer.Direction(transfer.direction)]:
        raise HttpError(400, "Netinkamas kasos dokumentas šiai krypčiai")
    if transfer.doc_number:
        return
    year = transfer.date.year
    if transfer.direction == MoneyTransfer.Direction.IN and transfer.doc_type in ("kpo", "ppk"):
        transfer.doc_number = next_cash_doc_number(transfer.tenant, transfer.doc_type, year)
    elif transfer.doc_type == "kio":
        transfer.doc_number = next_kio_number(transfer.tenant, year)


def allocate(
    transfer: MoneyTransfer,
    amount: Decimal,
    *,
    invoice_id: int | None = None,
    purchase_id: int | None = None,
    exchange_rate: Decimal | None = None,
    doc_type: str = "",
    doc_number: str = "",
):
    """Sudengia mokėjimo dalį su sąskaita (gauta) arba pirkimu (sumokėta)."""
    amount = amount.quantize(CENT)
    if amount <= 0:
        raise HttpError(400, "Sudengiama suma turi būti teigiama")
    if transfer.ignored:
        raise HttpError(400, "Neapskaitomas mokėjimas negali būti sudengtas")
    if (invoice_id is None) == (purchase_id is None):
        raise HttpError(400, "Nurodykite vieną dokumentą")
    with transaction.atomic():
        transfer = MoneyTransfer.objects.select_for_update().get(pk=transfer.pk)
        if amount > transfer.unallocated:
            raise HttpError(400, f"Nesudengtas mokėjimo likutis tik {transfer.unallocated}")
        if invoice_id is not None:
            return _allocate_invoice(transfer, amount, invoice_id, doc_type, doc_number)
        assert purchase_id is not None
        return _allocate_purchase(
            transfer, amount, purchase_id, exchange_rate, doc_type, doc_number
        )


def _allocate_invoice(
    transfer: MoneyTransfer, amount: Decimal, invoice_id: int, doc_type: str, doc_number: str
):
    if transfer.direction != MoneyTransfer.Direction.IN:
        raise HttpError(400, "Sąskaitas galima dengti tik gautais mokėjimais")
    invoice = (
        Invoice.objects.select_for_update().filter(tenant=transfer.tenant, id=invoice_id).first()
    )
    if invoice is None:
        raise HttpError(404, "Sąskaita nerasta")
    if invoice.status not in (*OPEN_INVOICE, Invoice.Status.PAID):
        raise HttpError(400, "Mokėjimai galimi tik išrašytai sąskaitai")
    if invoice.currency != transfer.currency:
        raise HttpError(400, "Sąskaitos ir mokėjimo valiutos skiriasi")
    if amount > invoice_remaining(invoice):
        raise HttpError(400, f"Sąskaitos likutis tik {invoice_remaining(invoice)}")
    if doc_type not in Payment.DocType.values:
        raise HttpError(400, "Netinkamas kasos dokumentas")
    if not doc_number and doc_type in (Payment.DocType.KPO, Payment.DocType.PPK):
        doc_number = next_cash_doc_number(transfer.tenant, doc_type, transfer.date.year)
    payment = invoice.payments.create(
        transfer=transfer,
        amount=amount,
        paid_at=transfer.date,
        method=transfer.method,
        doc_type=doc_type,
        doc_number=doc_number,
        note=(transfer.note or transfer.reference)[:200],
    )
    invoice.recalc_status()
    invoice.save(update_fields=["status", "updated_at"])
    return payment


def _allocate_purchase(
    transfer: MoneyTransfer,
    amount: Decimal,
    purchase_id: int,
    exchange_rate: Decimal | None,
    doc_type: str,
    doc_number: str = "",
):
    if transfer.direction != MoneyTransfer.Direction.OUT:
        raise HttpError(400, "Pirkimus galima dengti tik sumokėtais mokėjimais")
    purchase = (
        Purchase.objects.select_for_update().filter(tenant=transfer.tenant, id=purchase_id).first()
    )
    if purchase is None:
        raise HttpError(404, "Pirkinys nerastas")
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Mokėjimai negalimi anuliuotam pirkiniui")
    rate = exchange_rate or purchase.exchange_rate
    if rate <= 0:
        raise HttpError(400, "Netinkamas valiutos kursas")
    if purchase.currency == transfer.currency:
        amount_original = amount
    elif transfer.currency == MoneyTransfer.Currency.EUR:
        amount_original = (amount / rate).quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        raise HttpError(400, "Pirkinio ir mokėjimo valiutos skiriasi")
    if amount_original > purchase_remaining(purchase):
        raise HttpError(400, f"Pirkinio likutis tik {purchase_remaining(purchase)}")
    if doc_type not in PurchasePayment.DocType.values:
        raise HttpError(400, "Netinkamas kasos dokumentas")
    if not doc_number and doc_type == PurchasePayment.DocType.KIO:
        doc_number = next_kio_number(transfer.tenant, transfer.date.year)
    payment = purchase.payments.create(
        transfer=transfer,
        amount_original=amount_original,
        exchange_rate=rate,
        paid_at=transfer.date,
        method=transfer.method,
        doc_type=doc_type,
        doc_number=doc_number,
        note=(transfer.note or transfer.reference)[:200],
    )
    if purchase.currency != transfer.currency:
        # EUR mokėjimas už PLN pirkinį: EUR suma imama tiksliai iš banko.
        PurchasePayment.objects.filter(pk=payment.pk).update(amount_eur=amount)
        payment.amount_eur = amount
    purchase.recalc_status()
    purchase.save(update_fields=["status", "updated_at"])
    return payment


def unallocate(payment) -> None:
    doc = payment.invoice if isinstance(payment, Payment) else payment.purchase
    with transaction.atomic():
        payment.delete()
        doc.recalc_status()
        doc.save(update_fields=["status", "updated_at"])


def delete_transfer(transfer: MoneyTransfer) -> None:
    with transaction.atomic():
        docs: list[Invoice | Purchase] = [
            p.invoice for p in transfer.invoice_allocations.select_related("invoice")
        ]
        docs += [p.purchase for p in transfer.purchase_allocations.select_related("purchase")]
        transfer.delete()
        for doc in docs:
            doc.recalc_status()
            doc.save(update_fields=["status", "updated_at"])


def resync_allocations(transfer: MoneyTransfer) -> None:
    """Pakeitus mokėjimo datą/būdą, atnaujina sudengimų datas (pinigų principas)."""
    transfer.invoice_allocations.update(paid_at=transfer.date, method=transfer.method)
    transfer.purchase_allocations.update(paid_at=transfer.date, method=transfer.method)


_LEGAL_FORMS = {"uab", "mb", "ab", "ii", "vsi", "ij", "kb", "ou", "sia", "as", "ltd", "llc", "gmbh"}


def _norm_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in name.casefold())
    cleaned = cleaned.replace("į", "i").replace("š", "s")
    return " ".join(w for w in cleaned.split() if w not in _LEGAL_FORMS)


def own_accounts(tenant) -> set[str]:
    """Veiklos sąskaitos: profilio IBAN ir anksčiau importuotų išrašų sąskaitos."""
    accounts = set(
        MoneyTransfer.objects.filter(tenant=tenant)
        .exclude(account_iban="")
        .values_list("account_iban", flat=True)
        .distinct()
    )
    from apps.tenancy.models import SellerProfile

    iban = SellerProfile.objects.filter(tenant=tenant).values_list("iban", flat=True).first()
    if iban:
        accounts.add(iban.replace(" ", "").upper())
    return accounts


def match_counterparty(tenant, entry, *, cache: dict | None = None):
    """Kontragentas pagal įmonės kodą, tada pagal tikslų (normalizuotą) pavadinimą."""
    from apps.invoicing.models import Counterparty

    if cache is None:
        cache = {}
    if "by_code" not in cache:
        by_code: dict[str, list[int]] = {}
        by_name: dict[str, list[int]] = {}
        for cp in Counterparty.objects.filter(tenant=tenant).only("id", "name", "code"):
            if cp.code:
                by_code.setdefault(cp.code.strip(), []).append(cp.id)
            by_name.setdefault(_norm_name(cp.name), []).append(cp.id)
        cache["by_code"], cache["by_name"] = by_code, by_name
    ids = cache["by_code"].get(entry.counterparty_code) if entry.counterparty_code else None
    if not ids and entry.counterparty_name:
        ids = cache["by_name"].get(_norm_name(entry.counterparty_name))
    return ids[0] if ids and len(ids) == 1 else None


def preview_statements(tenant, statements) -> dict:
    """Sužymi dublikatus, savas sąskaitas ir kontragentus; nieko neįrašo."""
    own = own_accounts(tenant) | {s.account_iban for s in statements}
    cache: dict = {}
    rows = []
    for stmt in statements:
        existing = set(
            MoneyTransfer.objects.filter(
                tenant=tenant,
                account_iban=stmt.account_iban,
                external_id__in=[e.external_id for e in stmt.entries],
            ).values_list("external_id", flat=True)
        )
        for e in stmt.entries:
            if e.counterparty_iban and e.counterparty_iban in own:
                e.own_transfer = True
            rows.append(
                {
                    "account_iban": stmt.account_iban,
                    "external_id": e.external_id,
                    "direction": e.direction,
                    "date": e.date,
                    "amount": e.amount,
                    "currency": e.currency,
                    "method": e.method,
                    "counterparty_name": e.counterparty_name,
                    "counterparty_iban": e.counterparty_iban,
                    "counterparty_code": e.counterparty_code,
                    "counterparty_id": match_counterparty(tenant, e, cache=cache),
                    "reference": e.reference,
                    "bank_code": e.bank_code,
                    "own_transfer": e.own_transfer,
                    "duplicate": e.external_id in existing,
                    "supported": e.currency in MoneyTransfer.Currency.values,
                }
            )
    return {
        "statements": [
            {
                "account_iban": s.account_iban,
                "currency": s.currency,
                "bank_name": s.bank_name,
                "owner_name": s.owner_name,
                "period_from": s.period_from,
                "period_to": s.period_to,
                "entries": len(s.entries),
                "skipped": s.skipped,
            }
            for s in statements
        ],
        "entries": rows,
        "new_count": sum(1 for r in rows if not r["duplicate"] and r["supported"]),
        "duplicate_count": sum(1 for r in rows if r["duplicate"]),
        "unsupported_count": sum(1 for r in rows if not r["supported"]),
    }


def import_statements(tenant, user, statements, *, file_name: str, ignored_ids: set[str]):
    """Įrašo naujas operacijas kaip nesudengtus mokėjimus. Kartotinis importas saugus."""
    from apps.payments.models import BankImport

    preview = preview_statements(tenant, statements)
    created = 0
    with transaction.atomic():
        imports: dict[str, BankImport] = {}
        for s in statements:
            if s.account_iban not in imports:
                imports[s.account_iban] = BankImport.objects.create(
                    tenant=tenant,
                    account_iban=s.account_iban,
                    bank_name=s.bank_name[:200],
                    period_from=s.period_from,
                    period_to=s.period_to,
                    file_name=file_name[:255],
                    created_by=user if user is not None and user.is_authenticated else None,
                )
        for r in preview["entries"]:
            if r["duplicate"] or not r["supported"]:
                continue
            key = f"{r['account_iban']}:{r['external_id']}"
            _, was_created = MoneyTransfer.objects.get_or_create(
                tenant=tenant,
                account_iban=r["account_iban"],
                external_id=r["external_id"],
                defaults={
                    "direction": r["direction"],
                    "date": r["date"],
                    "amount": r["amount"],
                    "currency": r["currency"],
                    "method": r["method"],
                    "counterparty_id": r["counterparty_id"],
                    "counterparty_name": r["counterparty_name"],
                    "counterparty_iban": r["counterparty_iban"],
                    "reference": r["reference"],
                    "ignored": key in ignored_ids,
                    "source": MoneyTransfer.Source.IMPORT,
                    "bank_import": imports[r["account_iban"]],
                },
            )
            r["duplicate"] = not was_created
            created += int(was_created)
        for bi in imports.values():
            rows = [r for r in preview["entries"] if r["account_iban"] == bi.account_iban]
            bi.created_count = bi.transfers.count()
            bi.duplicate_count = sum(1 for r in rows if r["duplicate"])
            bi.save(update_fields=["created_count", "duplicate_count"])
    preview["created_count"] = created
    preview["new_count"] = 0
    return preview
