from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError

from apps.ledger.models import Category
from apps.purchases.models import Purchase, PurchasePayment, Supplier
from apps.purchases.schemas import (
    PurchaseIn,
    PurchaseOut,
    PurchasePaymentIn,
    PurchasePaymentOut,
    SupplierIn,
    SupplierOut,
)
from apps.purchases.services import generate_kio_pdf, next_kio_number
from apps.tenancy.api import current_tenant
from apps.tenancy.models import Tenant

router = Router()


def get_supplier(tenant: Tenant, supplier_id: int) -> Supplier:
    return get_object_or_404(Supplier, id=supplier_id, tenant=tenant)


def get_purchase(tenant: Tenant, purchase_id: int) -> Purchase:
    return get_object_or_404(
        Purchase.objects.select_related("supplier", "category").prefetch_related(
            "lines", "payments"
        ),
        id=purchase_id,
        tenant=tenant,
    )


# --- Suppliers ---


@router.get("/suppliers", response=list[SupplierOut])
def list_suppliers(request):
    return Supplier.objects.filter(tenant=current_tenant(request))


@router.post("/suppliers", response={201: SupplierOut})
def create_supplier(request, data: SupplierIn):
    supplier = Supplier.objects.create(tenant=current_tenant(request), **data.model_dump())
    return Status(201, supplier)


@router.get("/suppliers/{supplier_id}", response=SupplierOut)
def get_supplier_view(request, supplier_id: int):
    return get_supplier(current_tenant(request), supplier_id)


@router.put("/suppliers/{supplier_id}", response=SupplierOut)
def update_supplier(request, supplier_id: int, data: SupplierIn):
    supplier = get_supplier(current_tenant(request), supplier_id)
    for key, value in data.model_dump().items():
        setattr(supplier, key, value)
    supplier.save()
    return supplier


@router.delete("/suppliers/{supplier_id}", response={204: None})
def delete_supplier(request, supplier_id: int):
    get_supplier(current_tenant(request), supplier_id).delete()
    return Status(204, None)


# --- Purchases ---


def _purchase_values(tenant: Tenant, data: PurchaseIn) -> dict:
    values = data.model_dump(exclude={"supplier_id", "category_id", "lines"})
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
    if purchase.payments.exists():
        raise HttpError(400, "Pirkinys turi mokėjimų – redaguoti negalima")
    if not data.lines:
        raise HttpError(400, "Pirkinys turi turėti bent vieną eilutę")
    with transaction.atomic():
        for key, value in _purchase_values(tenant, data).items():
            setattr(purchase, key, value)
        purchase.lines.all().delete()
        for i, line in enumerate(data.lines):
            purchase.lines.create(**line.model_dump(), order=i)
        purchase.recalc_total()
        purchase.save()
    return get_purchase(tenant, purchase.id)


@router.delete("/purchases/{purchase_id}", response={204: None})
def delete_purchase(request, purchase_id: int):
    purchase = get_purchase(current_tenant(request), purchase_id)
    if purchase.payments.exists():
        raise HttpError(400, "Pirkinys turi mokėjimų – pirmiausia juos anuliuokite (kreipkitės)")
    purchase.delete()
    return Status(204, None)


@router.post("/purchases/{purchase_id}/cancel", response=PurchaseOut)
def cancel_purchase(request, purchase_id: int):
    purchase = get_purchase(current_tenant(request), purchase_id)
    if purchase.status == Purchase.Status.CANCELLED:
        raise HttpError(400, "Pirkinys jau anuliuotas")
    if purchase.payments.exists():
        raise HttpError(400, "Negalima anuliuoti pirkinio su mokėjimais")
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
