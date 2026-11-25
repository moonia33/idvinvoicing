import json
from datetime import date

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.invoicing.models import Counterparty, Invoice, Payment
from apps.payments import camt
from apps.payments.models import MoneyTransfer
from apps.payments.schemas import (
    AllocationIn,
    ImportResultOut,
    OpenDocumentOut,
    TransferIn,
    TransferOut,
    TransferUpdateIn,
)
from apps.payments.services import (
    OPEN_INVOICE,
    OPEN_PURCHASE,
    allocate,
    allocation_doc_number,
    assign_cash_doc,
    delete_transfer,
    import_statements,
    preview_statements,
    resync_allocations,
    unallocate,
)
from apps.purchases.models import Purchase, PurchasePayment
from apps.tenancy.api import current_tenant
from apps.tenancy.models import Tenant

router = Router(tags=["payments"])


def _qs(tenant: Tenant):
    return (
        MoneyTransfer.objects.filter(tenant=tenant)
        .select_related("counterparty")
        .prefetch_related("invoice_allocations__invoice", "purchase_allocations__purchase")
    )


def _purchase_label(p: Purchase) -> str:
    return p.doc_number or f"Pirkinys #{p.pk}"


def _out(t: MoneyTransfer) -> dict:
    allocations = [
        {
            "id": a.id,
            "kind": "invoice",
            "document_id": a.invoice_id,
            "document_label": a.invoice.full_number or f"Sąskaita #{a.invoice_id}",
            "amount": a.amount,
            "doc_type": a.doc_type,
            "doc_number": a.doc_number,
        }
        for a in t.invoice_allocations.all()
    ] + [
        {
            "id": a.id,
            "kind": "purchase",
            "document_id": a.purchase_id,
            "document_label": _purchase_label(a.purchase),
            "amount": t.allocation_amount(a),
            "doc_type": a.doc_type,
            "doc_number": a.doc_number,
        }
        for a in t.purchase_allocations.all()
    ]
    return {
        "id": t.id,
        "direction": t.direction,
        "date": t.date,
        "amount": t.amount,
        "currency": t.currency,
        "method": t.method,
        "counterparty_id": t.counterparty_id,
        "counterparty_display": (t.counterparty.name if t.counterparty else t.counterparty_name),
        "counterparty_name": t.counterparty_name,
        "counterparty_iban": t.counterparty_iban,
        "reference": t.reference,
        "note": t.note,
        "ignored": t.ignored,
        "doc_type": t.doc_type,
        "doc_number": t.doc_number,
        "account_iban": t.account_iban,
        "bank_import_id": t.bank_import_id,
        "source": t.source,
        "status": t.status,
        "allocated_total": t.allocated_total,
        "unallocated": t.unallocated,
        "allocations": allocations,
    }


def _get(tenant: Tenant, transfer_id: int) -> MoneyTransfer:
    return get_object_or_404(_qs(tenant), id=transfer_id)


def _counterparty(tenant: Tenant, counterparty_id: int | None) -> Counterparty | None:
    if counterparty_id is None:
        return None
    return get_object_or_404(Counterparty, tenant=tenant, id=counterparty_id)


@router.get("/transfers", response=list[TransferOut])
def list_transfers(
    request,
    direction: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    counterparty_id: int | None = None,
    q: str | None = None,
    source: str | None = None,
    bank_import: int | None = None,
):
    qs = _qs(current_tenant(request))
    if source in MoneyTransfer.Source.values:
        qs = qs.filter(source=source)
    if bank_import:
        qs = qs.filter(bank_import_id=bank_import)
    if direction in MoneyTransfer.Direction.values:
        qs = qs.filter(direction=direction)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if counterparty_id:
        qs = qs.filter(counterparty_id=counterparty_id)
    if q:
        qs = qs.filter(
            Q(counterparty__name__icontains=q)
            | Q(counterparty_name__icontains=q)
            | Q(reference__icontains=q)
            | Q(note__icontains=q)
            | Q(doc_number__icontains=q)
        )
    items = [_out(t) for t in qs]
    if status in MoneyTransfer.Status.values:
        items = [i for i in items if i["status"] == status]
    elif status == "open":  # nesudengti ir dalinai sudengti
        items = [
            i
            for i in items
            if i["status"] in (MoneyTransfer.Status.UNALLOCATED, MoneyTransfer.Status.PARTIAL)
        ]
    return items


@router.get("/transfers/open-documents", response=list[OpenDocumentOut])
def open_documents(request, direction: str, counterparty_id: int | None = None):
    """Neapmokėti dokumentai sudengimui, seniausi viršuje."""
    tenant = current_tenant(request)
    docs: list[dict] = []
    if direction == MoneyTransfer.Direction.IN:
        invoices = (
            Invoice.objects.filter(tenant=tenant, status__in=OPEN_INVOICE)
            .select_related("client")
            .prefetch_related("payments")
            .order_by("issue_date", "id")
        )
        if counterparty_id:
            invoices = invoices.filter(client_id=counterparty_id)
        for inv in invoices:
            remaining = inv.total - inv.paid_total
            if remaining > 0:
                docs.append(
                    {
                        "kind": "invoice",
                        "id": inv.id,
                        "label": inv.full_number,
                        "counterparty_id": inv.client_id,
                        "counterparty_name": inv.client.name,
                        "date": inv.issue_date,
                        "due_date": inv.due_date,
                        "currency": inv.currency,
                        "total": inv.total,
                        "remaining": remaining,
                    }
                )
    elif direction == MoneyTransfer.Direction.OUT:
        purchases = (
            Purchase.objects.filter(tenant=tenant, status__in=OPEN_PURCHASE)
            .select_related("supplier")
            .prefetch_related("payments")
            .order_by("document_date", "id")
        )
        if counterparty_id:
            purchases = purchases.filter(supplier_id=counterparty_id)
        for pur in purchases:
            remaining = pur.total - pur.paid_total
            if remaining > 0:
                docs.append(
                    {
                        "kind": "purchase",
                        "id": pur.id,
                        "label": _purchase_label(pur),
                        "counterparty_id": pur.supplier_id,
                        "counterparty_name": pur.supplier.name,
                        "date": pur.document_date,
                        "due_date": pur.due_date,
                        "currency": pur.currency,
                        "total": pur.total,
                        "remaining": remaining,
                    }
                )
    else:
        raise HttpError(400, "Netinkama kryptis")
    return docs


@router.post("/transfers/import", response=ImportResultOut)
def import_bank_statement(
    request,
    file: UploadedFile = File(...),  # noqa: B008
    commit: bool = Form(False),  # noqa: B008
    ignored: str = Form(""),  # noqa: B008
    tenant_id: int | None = Form(None),  # noqa: B008
):
    """camt.053 XML: be `commit` – tik peržiūra; su `commit` – įrašo naujas operacijas."""
    tenant = current_tenant(request)
    if tenant_id is not None and tenant_id != tenant.id:
        raise HttpError(409, "Pasikeitė aktyvi veikla – įkelkite išrašą iš naujo")
    if file.size and file.size > camt.MAX_FILE_SIZE:
        raise HttpError(400, "Failas per didelis (daugiausia 10 MB)")
    try:
        statements = camt.parse(file.read(camt.MAX_FILE_SIZE + 1))
    except camt.CamtError as e:
        raise HttpError(400, str(e)) from e
    if not commit:
        return preview_statements(tenant, statements)
    try:
        ignored_ids = {str(i) for i in json.loads(ignored or "[]")}
    except (ValueError, TypeError) as e:
        raise HttpError(400, "Netinkamas neapskaitomų operacijų sąrašas") from e
    return import_statements(
        tenant, request.user, statements, file_name=file.name or "", ignored_ids=ignored_ids
    )


@router.get("/transfers/{transfer_id}", response=TransferOut)
def get_transfer(request, transfer_id: int):
    return _out(_get(current_tenant(request), transfer_id))


@router.post("/transfers", response={201: TransferOut})
def create_transfer(request, data: TransferIn):
    tenant = current_tenant(request)
    if data.ignored and data.allocations:
        raise HttpError(400, "Neapskaitomas mokėjimas negali būti sudengtas")
    values = data.model_dump(exclude={"allocations", "counterparty_id"})
    with transaction.atomic():
        transfer = MoneyTransfer(
            tenant=tenant, counterparty=_counterparty(tenant, data.counterparty_id), **values
        )
        assign_cash_doc(transfer, number=not data.allocations)
        transfer.save()
        numbers = [
            allocate(
                transfer,
                a.amount,
                invoice_id=a.invoice_id,
                purchase_id=a.purchase_id,
                exchange_rate=a.exchange_rate,
                doc_type=transfer.doc_type,
                doc_number=transfer.doc_number,
            ).doc_number
            for a in data.allocations
        ]
        if transfer.doc_type and not transfer.doc_number and numbers:
            transfer.doc_number = ", ".join(n for n in numbers if n)[:40]
            transfer.save(update_fields=["doc_number"])
    return Status(201, _out(_get(tenant, transfer.id)))


@router.put("/transfers/{transfer_id}", response=TransferOut)
def update_transfer(request, transfer_id: int, data: TransferUpdateIn):
    tenant = current_tenant(request)
    transfer = _get(tenant, transfer_id)
    if transfer.source == MoneyTransfer.Source.IMPORT and (
        data.amount != transfer.amount or data.date != transfer.date
    ):
        raise HttpError(400, "Importuotos operacijos suma ir data nekeičiamos")
    if data.ignored and transfer.allocated_total > 0:
        raise HttpError(400, "Pirmiausia panaikinkite sudengimus")
    if data.amount < transfer.allocated_total:
        raise HttpError(400, f"Suma negali būti mažesnė už sudengtą ({transfer.allocated_total})")
    with transaction.atomic():
        for key, value in data.model_dump(exclude={"counterparty_id"}).items():
            setattr(transfer, key, value)
        transfer.counterparty = _counterparty(tenant, data.counterparty_id)
        transfer.mirror = False
        transfer.save()
        resync_allocations(transfer)
    return _out(_get(tenant, transfer.id))


@router.delete("/transfers/{transfer_id}", response={204: None})
def remove_transfer(request, transfer_id: int):
    delete_transfer(_get(current_tenant(request), transfer_id))
    return Status(204, None)


@router.post("/transfers/{transfer_id}/allocations", response={201: TransferOut})
def add_allocation(request, transfer_id: int, data: AllocationIn):
    tenant = current_tenant(request)
    transfer = _get(tenant, transfer_id)
    allocate(
        transfer,
        data.amount,
        invoice_id=data.invoice_id,
        purchase_id=data.purchase_id,
        exchange_rate=data.exchange_rate,
        doc_type=transfer.doc_type,
        doc_number=allocation_doc_number(transfer),
    )
    return Status(201, _out(_get(tenant, transfer.id)))


@router.delete("/transfers/{transfer_id}/allocations/{kind}/{allocation_id}", response=TransferOut)
def remove_allocation(request, transfer_id: int, kind: str, allocation_id: int):
    tenant = current_tenant(request)
    transfer = _get(tenant, transfer_id)
    model = {"invoice": Payment, "purchase": PurchasePayment}.get(kind)
    if model is None:
        raise HttpError(400, "Netinkamas sudengimo tipas")
    payment = get_object_or_404(model, id=allocation_id, transfer=transfer)
    unallocate(payment)
    return _out(_get(tenant, transfer.id))
