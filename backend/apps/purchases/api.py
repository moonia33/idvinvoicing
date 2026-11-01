from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError

from apps.invoicing.models import Counterparty
from apps.invoicing.schemas import ContactIn, ContactOut
from apps.ledger.models import Category
from apps.purchases.models import Purchase, PurchasePayment
from apps.purchases.schemas import (
    PurchaseIn,
    PurchaseOut,
    PurchasePaymentIn,
    PurchasePaymentOut,
)
from apps.purchases.services import generate_kio_pdf, next_kio_number
from apps.tenancy.api import current_tenant
from apps.tenancy.models import Tenant

router = Router()


def get_supplier(tenant: Tenant, supplier_id: int) -> Counterparty:
    return get_object_or_404(Counterparty, id=supplier_id, tenant=tenant)


def get_purchase(tenant: Tenant, purchase_id: int) -> Purchase:
    return get_object_or_404(
        Purchase.objects.select_related("supplier", "category").prefetch_related(
            "lines", "payments"
        ),
        id=purchase_id,
        tenant=tenant,
    )


# --- Suppliers (kontaktai su is_supplier=True; bendra lentelė su klientais) ---


@router.get("/suppliers", response=list[ContactOut])
def list_suppliers(request):
    return Counterparty.objects.filter(tenant=current_tenant(request), is_supplier=True)


@router.post("/suppliers", response={201: ContactOut})
def create_supplier(request, data: ContactIn):
    values = data.model_dump()
    values["is_supplier"] = True
    contact = Counterparty.objects.create(tenant=current_tenant(request), **values)
    return Status(201, contact)


@router.get("/suppliers/{supplier_id}", response=ContactOut)
def get_supplier_view(request, supplier_id: int):
    return get_supplier(current_tenant(request), supplier_id)


@router.put("/suppliers/{supplier_id}", response=ContactOut)
def update_supplier(request, supplier_id: int, data: ContactIn):
    supplier = get_supplier(current_tenant(request), supplier_id)
    values = data.model_dump()
    if not values["is_client"] and not values["is_supplier"]:
        values["is_client"] = supplier.is_client
        values["is_supplier"] = supplier.is_supplier
    for key, value in values.items():
        setattr(supplier, key, value)
    supplier.save()
    return supplier


@router.delete("/suppliers/{supplier_id}", response={204: None})
def delete_supplier(request, supplier_id: int):
    get_supplier(current_tenant(request), supplier_id).delete()
    return Status(204, None)


# --- Purchases ---


def _purchase_values(tenant: Tenant, data: PurchaseIn) -> dict:
    values = data.model_dump(exclude={"supplier_id", "category_id", "lines", "paid_now"})
    values["supplier"] = get_supplier(tenant, data.supplier_id)
    if data.category_id:
        values["category"] = get_object_or_404(
            Category, id=data.category_id, tenant=tenant, kind="expense"
        )
    else:
        values["category"] = None
    return values


@router.get("/purchases", response=list[PurchaseOut])
def list_purchases(request, status: str | None = None, year: int | None = None):
    qs = (
        Purchase.objects.filter(tenant=current_tenant(request))
        .select_related("supplier", "category")
        .prefetch_related("lines", "payments")
    )
    if status:
        qs = qs.filter(status=status)
    if year:
        qs = qs.filter(document_date__year=year)
    return qs


@router.post("/purchases", response={201: PurchaseOut})
def create_purchase(request, data: PurchaseIn):
    tenant = current_tenant(request)
    if not data.lines:
        raise HttpError(400, "Pirkinys turi turėti bent vieną eilutę")
    with transaction.atomic():
        purchase = Purchase.objects.create(tenant=tenant, **_purchase_values(tenant, data))
        for i, line in enumerate(data.lines):
            purchase.lines.create(**line.model_dump(), order=i)
        purchase.recalc_total()
        purchase.save(update_fields=["total"])
        if data.paid_now:
            purchase.payments.create(
                amount_original=purchase.total,
                exchange_rate=purchase.exchange_rate,
                paid_at=purchase.document_date,
                method=(
                    PurchasePayment.Method.BANK
                    if data.doc_type == Purchase.DocType.SF
                    else PurchasePayment.Method.CASH
                ),
                doc_type=(
                    PurchasePayment.DocType.KIO
                    if data.doc_type == Purchase.DocType.KIO
                    else (
                        PurchasePayment.DocType.PPK
                        if data.doc_type == Purchase.DocType.PPK
                        else PurchasePayment.DocType.NONE
                    )
                ),
                doc_number=(
                    next_kio_number(tenant, purchase.document_date.year)
                    if data.doc_type == Purchase.DocType.KIO
                    else purchase.doc_number
                ),
            )
            purchase.recalc_status()
            purchase.save(update_fields=["status", "updated_at"])
    return Status(201, get_purchase(tenant, purchase.id))


@router.get("/purchases/{purchase_id}", response=PurchaseOut)
def get_purchase_view(request, purchase_id: int):
    return get_purchase(current_tenant(request), purchase_id)


@router.put("/purchases/{purchase_id}", response=PurchaseOut)
def update_purchase(request, purchase_id: int, data: PurchaseIn):
    tenant = current_tenant(request)
    purchase = get_purchase(tenant, purchase_id)
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Anuliuoto pirkinio redaguoti negalima")
    if not data.lines:
        raise HttpError(400, "Pirkinys turi turėti bent vieną eilutę")
    with transaction.atomic():
        for key, value in _purchase_values(tenant, data).items():
            setattr(purchase, key, value)
        purchase.lines.all().delete()
        for i, line in enumerate(data.lines):
            purchase.lines.create(**line.model_dump(), order=i)
        purchase.recalc_total()
        purchase.recalc_status()
        purchase.save()
    return get_purchase(tenant, purchase.id)


@router.delete("/purchases/{purchase_id}", response={204: None})
def delete_purchase(request, purchase_id: int):
    purchase = get_purchase(current_tenant(request), purchase_id)
    purchase.delete()  # mokėjimai/eilutės – CASCADE
    return Status(204, None)


@router.post("/purchases/{purchase_id}/cancel", response=PurchaseOut)
def cancel_purchase(request, purchase_id: int):
    purchase = get_purchase(current_tenant(request), purchase_id)
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Pirkinys jau anuliuotas")
    with transaction.atomic():
        purchase.payments.all().delete()  # anuliuojant – mokėjimai šalinami
        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status", "updated_at"])
    return purchase


@router.post("/purchases/{purchase_id}/payments", response={201: PurchasePaymentOut})
def add_purchase_payment(request, purchase_id: int, data: PurchasePaymentIn):
    purchase = get_purchase(current_tenant(request), purchase_id)
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Mokėjimai negalimi anuliuotam pirkiniui")
    payload = data.model_dump()
    if payload["exchange_rate"] is None:
        payload["exchange_rate"] = purchase.exchange_rate
    if data.doc_type == PurchasePayment.DocType.KIO and not payload["doc_number"]:
        payload["doc_number"] = next_kio_number(purchase.tenant, data.paid_at.year)
    with transaction.atomic():
        payment = purchase.payments.create(**payload)
        purchase.recalc_status()
        purchase.save(update_fields=["status", "updated_at"])
    return Status(201, payment)


def get_purchase_payment(tenant: Tenant, payment_id: int) -> PurchasePayment:
    return get_object_or_404(PurchasePayment, id=payment_id, purchase__tenant=tenant)


@router.put("/purchase-payments/{payment_id}", response=PurchasePaymentOut)
def update_purchase_payment(request, payment_id: int, data: PurchasePaymentIn):
    payment = get_purchase_payment(current_tenant(request), payment_id)
    purchase = payment.purchase
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Mokėjimai negalimi anuliuotam pirkiniui")
    payload = data.model_dump()
    if payload["exchange_rate"] is None:
        payload["exchange_rate"] = payment.exchange_rate
    with transaction.atomic():
        for key, value in payload.items():
            setattr(payment, key, value)
        payment.save()  # save() perskaičiuoja amount_eur
        purchase.recalc_status()
        purchase.save(update_fields=["status", "updated_at"])
    return payment


@router.delete("/purchase-payments/{payment_id}", response={204: None})
def delete_purchase_payment(request, payment_id: int):
    payment = get_purchase_payment(current_tenant(request), payment_id)
    purchase = payment.purchase
    with transaction.atomic():
        payment.delete()
        purchase.recalc_status()
        purchase.save(update_fields=["status", "updated_at"])
    return Status(204, None)


@router.get("/purchase-payments/{payment_id}/kio.pdf", response={200: None})
def kio_pdf(request, payment_id: int):
    payment = get_object_or_404(
        PurchasePayment, id=payment_id, purchase__tenant=current_tenant(request)
    )
    if payment.doc_type != PurchasePayment.DocType.KIO:
        raise HttpError(400, "KIO PDF galimas tik KIO mokėjimams")
    pdf = generate_kio_pdf(payment)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{payment.doc_number or "kio"}.pdf"'
    )
    return response
