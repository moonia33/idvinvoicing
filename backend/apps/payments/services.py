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


def transfer_for_invoice_payment(payment: Payment) -> MoneyTransfer:
    inv = payment.invoice
    return MoneyTransfer.objects.create(
        tenant=inv.tenant,
        direction=MoneyTransfer.Direction.IN,
        date=payment.paid_at,
        amount=payment.amount,
        currency=inv.currency,
        method=payment.method,
        counterparty=inv.client,
        note=payment.note,
    )


def transfer_for_purchase_payment(payment: PurchasePayment) -> MoneyTransfer:
    pur = payment.purchase
    return MoneyTransfer.objects.create(
        tenant=pur.tenant,
        direction=MoneyTransfer.Direction.OUT,
        date=payment.paid_at,
        amount=payment.amount_original,
        currency=pur.currency,
        method=payment.method,
        counterparty=pur.supplier,
        note=payment.note,
    )


def sync_single_transfer(transfer: MoneyTransfer | None, amount: Decimal, payment) -> None:
    """Dokumento puslapyje redaguojant mokėjimą, sinchronizuoja rankinį 1:1 mokėjimą."""
    if transfer is None:
        return
    if (
        transfer.source == MoneyTransfer.Source.MANUAL
        and transfer.invoice_allocations.count() + transfer.purchase_allocations.count() == 1
    ):
        transfer.amount = amount
        transfer.date = payment.paid_at
        transfer.method = payment.method
        transfer.save(update_fields=["amount", "date", "method"])
    elif transfer.unallocated < 0:
        raise HttpError(400, "Sudengta suma viršija banko operacijos sumą")


def cleanup_transfers(transfer_ids: Iterable[int | None]) -> None:
    """Pašalina rankinius mokėjimus, kurie liko be sudengimų (importuoti lieka)."""
    ids = {i for i in transfer_ids if i}
    MoneyTransfer.objects.filter(
        id__in=ids,
        source=MoneyTransfer.Source.MANUAL,
        invoice_allocations__isnull=True,
        purchase_allocations__isnull=True,
    ).delete()


def allocate(
    transfer: MoneyTransfer,
    amount: Decimal,
    *,
    invoice_id: int | None = None,
    purchase_id: int | None = None,
    exchange_rate: Decimal | None = None,
    doc_type: str = "",
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
            return _allocate_invoice(transfer, amount, invoice_id, doc_type)
        assert purchase_id is not None
        return _allocate_purchase(transfer, amount, purchase_id, exchange_rate, doc_type)


def _allocate_invoice(transfer: MoneyTransfer, amount: Decimal, invoice_id: int, doc_type: str):
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
    if doc_type not in ("", Payment.DocType.KPO, Payment.DocType.PPK):
        raise HttpError(400, "Netinkamas kasos dokumentas")
    payment = invoice.payments.create(
        transfer=transfer,
        amount=amount,
        paid_at=transfer.date,
        method=transfer.method,
        doc_type=doc_type,
        doc_number=(
            next_cash_doc_number(transfer.tenant, doc_type, transfer.date.year) if doc_type else ""
        ),
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
    if doc_type not in ("", PurchasePayment.DocType.KIO, PurchasePayment.DocType.PPK):
        raise HttpError(400, "Netinkamas kasos dokumentas")
    payment = purchase.payments.create(
        transfer=transfer,
        amount_original=amount_original,
        exchange_rate=rate,
        paid_at=transfer.date,
        method=transfer.method,
        doc_type=doc_type,
        doc_number=(
            next_kio_number(transfer.tenant, transfer.date.year)
            if doc_type == PurchasePayment.DocType.KIO
            else ""
        ),
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
