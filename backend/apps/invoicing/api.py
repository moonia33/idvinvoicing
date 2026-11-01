from datetime import date

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError

from apps.core.models import DocumentSequence
from apps.invoicing.models import (
    Counterparty,
    Invoice,
    Payment,
    RecurringTemplate,
    Service,
)
from apps.invoicing.schemas import (
    ContactIn,
    ContactOut,
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
from apps.invoicing.services import (
    generate_cash_doc_pdf,
    generate_invoice_pdf,
    issue_invoice,
    next_cash_doc_number,
)
from apps.tenancy.api import current_tenant
from apps.tenancy.models import Tenant

router = Router()


def get_client(tenant: Tenant, client_id: int) -> Counterparty:
    return get_object_or_404(Counterparty, id=client_id, tenant=tenant)


@router.get("/counterparties", response=list[ContactOut])
def list_counterparties(request):
    """Visi kontaktai – tiek klientai, tiek tiekėjai."""
    return Counterparty.objects.filter(tenant=current_tenant(request))


# --- Clients (kontaktai su is_client=True) ---


@router.get("/clients", response=list[ContactOut])
def list_clients(request):
    return Counterparty.objects.filter(tenant=current_tenant(request), is_client=True)


@router.post("/clients", response={201: ContactOut})
def create_client(request, data: ContactIn):
    values = data.model_dump()
    values["is_client"] = True
    contact = Counterparty.objects.create(tenant=current_tenant(request), **values)
    return Status(201, contact)


@router.get("/clients/{client_id}", response=ContactOut)
def get_client_view(request, client_id: int):
    return get_client(current_tenant(request), client_id)


@router.put("/clients/{client_id}", response=ContactOut)
def update_client(request, client_id: int, data: ContactIn):
    client = get_client(current_tenant(request), client_id)
    values = data.model_dump()
    if not values["is_client"] and not values["is_supplier"]:
        # flag'ai nenurodyti (seni klientai) – paliekame esamus
        values["is_client"] = client.is_client
        values["is_supplier"] = client.is_supplier
    for key, value in values.items():
        setattr(client, key, value)
    client.save()
    return client


@router.delete("/clients/{client_id}", response={204: None})
def delete_client(request, client_id: int):
    get_client(current_tenant(request), client_id).delete()
    return Status(204, None)


def get_invoice(tenant: Tenant, invoice_id: int) -> Invoice:
    return get_object_or_404(
        Invoice.objects.select_related("client").prefetch_related("lines", "payments"),
        id=invoice_id,
        tenant=tenant,
    )


# --- Services (katalogas) ---


def get_service(tenant: Tenant, service_id: int) -> Service:
    return get_object_or_404(Service, id=service_id, tenant=tenant)


def _service_values(tenant: Tenant, data: ServiceIn) -> dict:
    from apps.ledger.models import Category

    values = data.model_dump()
    category_id = values.pop("category_id")
    if category_id:
        values["category"] = get_object_or_404(Category, id=category_id, tenant=tenant)
    else:
        values["category"] = None
    return values


@router.get("/services", response=list[ServiceOut])
def list_services(request, all: bool = False, usage: str | None = None):
    qs = Service.objects.filter(tenant=current_tenant(request))
    if not all:
        qs = qs.filter(active=True)
    if usage == "sale":
        qs = qs.filter(is_sale=True)
    elif usage == "purchase":
        qs = qs.filter(is_purchase=True)
    return qs


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


def _chronology_conflict(
    tenant: Tenant,
    series: str,
    year: int,
    issue_date: date,
    number: int | None,
    exclude_id: int,
) -> Invoice | None:
    """Sąskaita, su kuria būtų pažeista numeracijos chronologija toje serijoje.

    number=None – naujas (suinteikiamas) numeris, didesnis už visus esamus.
    """
    others = Invoice.objects.filter(
        tenant=tenant,
        series=series,
        year=year,
        status__in=[
            Invoice.Status.ISSUED,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.PAID,
        ],
    ).exclude(pk=exclude_id)
    for o in others:
        if o.issue_date is None or o.issue_date == issue_date:
            continue
        if number is None:
            if o.issue_date > issue_date:
                return o
        elif o.number is not None and (o.issue_date < issue_date) == (o.number > number):
            return o
    return None


def _guard_chronology(
    tenant: Tenant,
    series: str,
    year: int,
    issue_date: date,
    number: int | None,
    exclude_id: int,
) -> None:
    other = _chronology_conflict(tenant, series, year, issue_date, number, exclude_id)
    if other is not None:
        raise HttpError(
            400,
            f"Numeracija su chronologija negali būti pažeista: {other.full_number} "
            f"išrašyta {other.issue_date}. Pakeiskite datą arba sąskaitos numerį/seriją.",
        )


@router.put("/invoices/{invoice_id}", response=InvoiceOut)
def update_invoice(request, invoice_id: int, data: InvoiceIn):
    tenant = current_tenant(request)
    invoice = get_invoice(tenant, invoice_id)
    if invoice.status == Invoice.Status.CANCELLED:
        raise HttpError(400, "Anuliuotos sąskaitos redaguoti negalima")
    if not data.lines:
        raise HttpError(400, "Sąskaita turi turėti bent vieną eilutę")
    if invoice.status != Invoice.Status.DRAFT:
        eff_series = data.series if data.series is not None else invoice.series
        eff_date = data.issue_date or invoice.issue_date or date.today()
        eff_year = data.year or eff_date.year
        eff_number = data.number if data.number is not None else invoice.number
        _guard_chronology(tenant, eff_series, eff_year, eff_date, eff_number, invoice.id)
    with transaction.atomic():
        invoice.client = get_client(tenant, data.client_id)
        invoice.due_date = data.due_date
        invoice.notes = data.notes
        if invoice.status != Invoice.Status.DRAFT:
            # korekcijos išrašytai sąskaitai: data ir numeracija
            if data.issue_date is not None:
                invoice.issue_date = data.issue_date
                invoice.year = data.issue_date.year
            if data.series is not None:
                invoice.series = data.series
            if data.year is not None:
                invoice.year = data.year
            if data.number is not None:
                invoice.number = data.number
        invoice.lines.all().delete()
        for i, line in enumerate(data.lines):
            invoice.lines.create(**line.model_dump(), order=i)
        invoice.recalc_total()
        invoice.recalc_status()
        try:
            invoice.save()
        except IntegrityError:
            raise HttpError(400, "Sąskaitos numeris jau užimtas") from None
    return get_invoice(tenant, invoice.id)


@router.post("/invoices/{invoice_id}/issue", response=InvoiceOut)
def issue_invoice_view(request, invoice_id: int, data: IssueIn):
    tenant = current_tenant(request)
    invoice = get_invoice(tenant, invoice_id)
    if invoice.status != Invoice.Status.DRAFT:
        raise HttpError(400, "Išrašyti galima tik juodraštį")
    if data.series:
        invoice.series = data.series
    issue_date = data.issue_date or date.today()
    _guard_chronology(
        tenant, invoice.series, issue_date.year, issue_date, None, invoice.id
    )
    try:
        issue_invoice(invoice, issue_date, data.due_date)
    except ValueError as e:
        raise HttpError(400, str(e)) from e
    return get_invoice(tenant, invoice.id)


@router.post("/invoices/{invoice_id}/cancel", response=InvoiceOut)
def cancel_invoice(request, invoice_id: int):
    invoice = get_invoice(current_tenant(request), invoice_id)
    if invoice.status == Invoice.Status.CANCELLED:
        raise HttpError(400, "Sąskaita jau atšaukta")
    with transaction.atomic():
        invoice.payments.all().delete()  # anuliuojant – mokėjimai šalinami
        invoice.status = Invoice.Status.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])
    return invoice


@router.post("/invoices/{invoice_id}/payments", response={201: PaymentOut})
def add_payment(request, invoice_id: int, data: PaymentIn):
    invoice = get_invoice(current_tenant(request), invoice_id)
    if invoice.status in (Invoice.Status.DRAFT, Invoice.Status.CANCELLED):
        raise HttpError(400, "Mokėjimai galimi tik išrašytai sąskaitai")
    payload = data.model_dump()
    if data.doc_type in (Payment.DocType.KPO, Payment.DocType.PPK) and not payload["doc_number"]:
        payload["doc_number"] = next_cash_doc_number(
            invoice.tenant, data.doc_type.value, data.paid_at.year
        )
    with transaction.atomic():
        payment = invoice.payments.create(**payload)
        invoice.recalc_status()
        invoice.save(update_fields=["status", "updated_at"])
    return Status(201, payment)


def get_payment(tenant: Tenant, payment_id: int) -> Payment:
    return get_object_or_404(Payment, id=payment_id, invoice__tenant=tenant)


@router.put("/payments/{payment_id}", response=PaymentOut)
def update_payment(request, payment_id: int, data: PaymentIn):
    payment = get_payment(current_tenant(request), payment_id)
    invoice = payment.invoice
    if invoice.status == Invoice.Status.CANCELLED:
        raise HttpError(400, "Mokėjimai negalimi anuliuotai sąskaitai")
    payload = data.model_dump()
    with transaction.atomic():
        for key, value in payload.items():
            setattr(payment, key, value)
        payment.save()
        invoice.recalc_status()
        invoice.save(update_fields=["status", "updated_at"])
    return payment


@router.delete("/payments/{payment_id}", response={204: None})
def delete_payment(request, payment_id: int):
    payment = get_payment(current_tenant(request), payment_id)
    invoice = payment.invoice
    with transaction.atomic():
        payment.delete()
        invoice.recalc_status()
        invoice.save(update_fields=["status", "updated_at"])
    return Status(204, None)


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
def invoice_pdf(request, invoice_id: int, with_cash_docs: bool = False):
    invoice = get_invoice(current_tenant(request), invoice_id)
    pdf = generate_invoice_pdf(invoice, with_cash_docs=with_cash_docs)
    response = HttpResponse(pdf, content_type="application/pdf")
    filename = invoice.full_number or f"juodrastis-{invoice.pk}"
    response["Content-Disposition"] = f'inline; filename="{filename}.pdf"'
    return response


@router.get("/payments/{payment_id}/cash-doc.pdf", response={200: None})
def cash_doc_pdf(request, payment_id: int):
    payment = get_object_or_404(Payment, id=payment_id, invoice__tenant=current_tenant(request))
    if payment.doc_type not in (Payment.DocType.KPO, Payment.DocType.PPK):
        raise HttpError(400, "Kasos dokumentas galimas tik KPO/PPK mokėjimams")
    pdf = generate_cash_doc_pdf(payment)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="{payment.doc_number or "kasos-dokumentas"}.pdf"'
    )
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
