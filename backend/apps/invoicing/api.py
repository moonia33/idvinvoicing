from datetime import date

from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError

from apps.core.models import DocumentSequence
from apps.invoicing.models import Client, Invoice, RecurringTemplate, Service
from apps.invoicing.schemas import (
    ClientIn,
    ClientOut,
    InvoiceIn,
    InvoiceOut,
    IssueIn,
    PaymentIn,
    PaymentOut,
    RecurringIn,
    RecurringOut,
    SendIn,
    ServiceIn,
    ServiceOut,
)
from apps.invoicing.services import generate_invoice_pdf, issue_invoice
from apps.tenancy.api import current_tenant
from apps.tenancy.models import Tenant

router = Router()


def get_client(tenant: Tenant, client_id: int) -> Client:
    return get_object_or_404(Client, id=client_id, tenant=tenant)


def get_invoice(tenant: Tenant, invoice_id: int) -> Invoice:
    return get_object_or_404(
        Invoice.objects.select_related("client").prefetch_related("lines", "payments"),
        id=invoice_id,
        tenant=tenant,
    )


# --- Clients ---


@router.get("/clients", response=list[ClientOut])
def list_clients(request):
    return Client.objects.filter(tenant=current_tenant(request))


@router.post("/clients", response={201: ClientOut})
def create_client(request, data: ClientIn):
    client = Client.objects.create(tenant=current_tenant(request), **data.model_dump())
    return Status(201, client)


@router.get("/clients/{client_id}", response=ClientOut)
def get_client_view(request, client_id: int):
    return get_client(current_tenant(request), client_id)


@router.put("/clients/{client_id}", response=ClientOut)
def update_client(request, client_id: int, data: ClientIn):
    client = get_client(current_tenant(request), client_id)
    for key, value in data.model_dump().items():
        setattr(client, key, value)
    client.save()
    return client


@router.delete("/clients/{client_id}", response={204: None})
def delete_client(request, client_id: int):
    get_client(current_tenant(request), client_id).delete()
    return Status(204, None)


# --- Services (katalogas) ---


def get_service(tenant: Tenant, service_id: int) -> Service:
    return get_object_or_404(Service, id=service_id, tenant=tenant)


def _service_values(tenant: Tenant, data: ServiceIn) -> dict:
    from apps.ledger.models import Category

    values = data.model_dump()
    category_id = values.pop("category_id")
    if category_id:
        values["category"] = get_object_or_404(
            Category, id=category_id, tenant=tenant, kind="income"
        )
    else:
        values["category"] = None
    return values


@router.get("/services", response=list[ServiceOut])
def list_services(request, all: bool = False):
    qs = Service.objects.filter(tenant=current_tenant(request))
    return qs if all else qs.filter(active=True)


@router.post("/services", response={201: ServiceOut})
def create_service(request, data: ServiceIn):
    tenant = current_tenant(request)
    service = Service.objects.create(tenant=tenant, **_service_values(tenant, data))
    return Status(201, service)


@router.put("/services/{service_id}", response=ServiceOut)
def update_service(request, service_id: int, data: ServiceIn):
    tenant = current_tenant(request)
    service = get_service(tenant, service_id)
    for key, value in _service_values(tenant, data).items():
        setattr(service, key, value)
    service.save()
    return service


@router.delete("/services/{service_id}", response={204: None})
def delete_service(request, service_id: int):
    get_service(current_tenant(request), service_id).delete()
    return Status(204, None)


# --- Invoices ---


@router.get("/invoices/next-number", response=dict)
def next_number_preview(request, year: int | None = None):
    """Numatomas kitas sąskaitos numeris (peržiūrai – nesunaudoja sekos)."""
    tenant = current_tenant(request)
    profile = getattr(tenant, "profile", None)
    series = profile.invoice_series if profile else "SF"
    year = year or date.today().year
    seq = DocumentSequence.objects.filter(
        tenant=tenant, kind="invoice", series=series, year=year
    ).first()
    n = (seq.last_number if seq else 0) + 1
    return {"full_number": f"{series}-{year}-{n:04d}", "series": series, "year": year}


@router.get("/invoices", response=list[InvoiceOut])
def list_invoices(request, status: str | None = None, client_id: int | None = None):
    qs = (
        Invoice.objects.filter(tenant=current_tenant(request))
        .select_related("client")
        .prefetch_related("lines", "payments")
    )
    if status:
        qs = qs.filter(status=status)
    if client_id:
        qs = qs.filter(client_id=client_id)
    return qs


@router.post("/invoices", response={201: InvoiceOut})
def create_invoice(request, data: InvoiceIn):
    tenant = current_tenant(request)
    client = get_client(tenant, data.client_id)
    if not data.lines:
        raise HttpError(400, "Sąskaita turi turėti bent vieną eilutę")
    with transaction.atomic():
        invoice = Invoice.objects.create(
            tenant=tenant,
            client=client,
            series=getattr(getattr(tenant, "profile", None), "invoice_series", None) or "SF",
            due_date=data.due_date,
            notes=data.notes,
        )
        for i, line in enumerate(data.lines):
            invoice.lines.create(**line.model_dump(), order=i)
        invoice.recalc_total()
        invoice.save(update_fields=["total"])
    return Status(201, get_invoice(tenant, invoice.id))


@router.get("/invoices/{invoice_id}", response=InvoiceOut)
def get_invoice_view(request, invoice_id: int):
    return get_invoice(current_tenant(request), invoice_id)


@router.put("/invoices/{invoice_id}", response=InvoiceOut)
def update_invoice(request, invoice_id: int, data: InvoiceIn):
    tenant = current_tenant(request)
    invoice = get_invoice(tenant, invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise HttpError(400, "Redaguoti galima tik juodraštį")
    if not data.lines:
        raise HttpError(400, "Sąskaita turi turėti bent vieną eilutę")
    with transaction.atomic():
        invoice.client = get_client(tenant, data.client_id)
        invoice.due_date = data.due_date
        invoice.notes = data.notes
        invoice.lines.all().delete()
        for i, line in enumerate(data.lines):
            invoice.lines.create(**line.model_dump(), order=i)
        invoice.recalc_total()
        invoice.save()
    return get_invoice(tenant, invoice.id)


@router.post("/invoices/{invoice_id}/issue", response=InvoiceOut)
def issue_invoice_view(request, invoice_id: int, data: IssueIn):
    tenant = current_tenant(request)
    invoice = get_invoice(tenant, invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise HttpError(400, "Išrašyti galima tik juodraštį")
    if data.series:
        invoice.series = data.series
    try:
        issue_invoice(invoice, data.issue_date or date.today(), data.due_date)
    except ValueError as e:
        raise HttpError(400, str(e)) from e
    return get_invoice(tenant, invoice.id)


@router.post("/invoices/{invoice_id}/cancel", response=InvoiceOut)
def cancel_invoice(request, invoice_id: int):
    invoice = get_invoice(current_tenant(request), invoice_id)
    if invoice.status == Invoice.Status.CANCELLED:
        raise HttpError(400, "Sąskaita jau atšaukta")
    if invoice.payments.exists():
        raise HttpError(400, "Negalima atšaukti sąskaitos su mokėjimais")
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])
    return invoice


@router.post("/invoices/{invoice_id}/payments", response={201: PaymentOut})
def add_payment(request, invoice_id: int, data: PaymentIn):
    invoice = get_invoice(current_tenant(request), invoice_id)
    if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.CANCELLED):
        raise HttpError(400, "Mokėjimai galimi tik išrašytai sąskaitai")
    with transaction.atomic():
        payment = invoice.payments.create(**data.model_dump())
        invoice.recalc_status()
        invoice.save(update_fields=["status", "updated_at"])
    return Status(201, payment)


@router.post("/invoices/{invoice_id}/send", response={200: dict, 400: dict})
def send_invoice(request, invoice_id: int, data: SendIn):
    from apps.mailer.services import queue_invoice_email  # lazy – circular

    invoice = get_invoice(current_tenant(request), invoice_id)
    if invoice.status == Invoice.Status.DRAFT:
        raise HttpError(400, "Pirmiausia išrašykite sąskaitą")
    recipient = data.to or invoice.client.email
    if not recipient:
        return Status(400, {"detail": "Nėra gavėjo el. pašto"})
    outbox = queue_invoice_email(invoice, recipient, data.subject, data.body)
    return Status(200, {"detail": "Laiškas įtrauktas į eilę", "outbox_id": outbox.id})


@router.get("/invoices/{invoice_id}/pdf", response={200: None})
def invoice_pdf(request, invoice_id: int):
    invoice = get_invoice(current_tenant(request), invoice_id)
    pdf = generate_invoice_pdf(invoice)
    response = HttpResponse(pdf, content_type="application/pdf")
    filename = invoice.full_number or f"juodrastis-{invoice.pk}"
    response["Content-Disposition"] = f'inline; filename="{filename}.pdf"'
    return response


# --- Recurring templates ---


@router.get("/recurring", response=list[RecurringOut])
def list_recurring(request):
    return (
        RecurringTemplate.objects.filter(tenant=current_tenant(request))
        .select_related("client")
        .prefetch_related("lines")
    )


@router.post("/recurring", response={201: RecurringOut})
def create_recurring(request, data: RecurringIn):
    tenant = current_tenant(request)
    client = get_client(tenant, data.client_id)
    if not data.lines:
        raise HttpError(400, "Šablonas turi turėti bent vieną eilutę")
    with transaction.atomic():
        tpl = RecurringTemplate.objects.create(
            tenant=tenant,
            client=client,
            **data.model_dump(exclude={"client_id", "lines"}),
        )
        for i, line in enumerate(data.lines):
            tpl.lines.create(**line.model_dump(), order=i)
    return Status(201, tpl)


@router.put("/recurring/{template_id}", response=RecurringOut)
def update_recurring(request, template_id: int, data: RecurringIn):
    tenant = current_tenant(request)
    tpl = get_object_or_404(RecurringTemplate, id=template_id, tenant=tenant)
    with transaction.atomic():
        tpl.client = get_client(tenant, data.client_id)
        for key, value in data.model_dump(exclude={"client_id", "lines"}).items():
            setattr(tpl, key, value)
        tpl.save()
        if data.lines:
            tpl.lines.all().delete()
            for i, line in enumerate(data.lines):
                tpl.lines.create(**line.model_dump(), order=i)
    return tpl


@router.delete("/recurring/{template_id}", response={204: None})
def delete_recurring(request, template_id: int):
    get_object_or_404(RecurringTemplate, id=template_id, tenant=current_tenant(request)).delete()
    return Status(204, None)
