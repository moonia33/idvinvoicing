import calendar
from datetime import date, timedelta

from django.db import transaction
from django.template.loader import render_to_string

from apps.core.numbering import next_document_number
from apps.invoicing.models import Invoice


def issue_invoice(invoice: Invoice, issue_date: date, due_date: date | None = None) -> Invoice:
    """Priskiria seriją/metus/numerį ir paverčia juodraštį išrašyta sąskaita."""
    if invoice.status != Invoice.Status.DRAFT:
        raise ValueError("Išrašyti galima tik juodraštį")
    if not invoice.lines.exists():
        raise ValueError("Sąskaita neturi eilučių")
    with transaction.atomic():
        invoice.year = issue_date.year
        invoice.number = next_document_number(
            invoice.tenant, "invoice", invoice.series, issue_date.year
        )
        invoice.issue_date = issue_date
        invoice.due_date = due_date or invoice.due_date or issue_date + timedelta(days=14)
        invoice.status = Invoice.Status.ISSUED
        invoice.save()
    return invoice


def generate_invoice_pdf(invoice: Invoice) -> bytes:
    """Sugeneruoja sąskaitos PDF baitus (WeasyPrint – tik Linux/Docker aplinkoje)."""
    from weasyprint import HTML  # lazy: Windows dev be GTK bibliotekų

    tenant = invoice.tenant
    html = render_to_string(
        "invoicing/invoice_pdf.html",
        {"invoice": invoice, "profile": getattr(tenant, "profile", None)},
    )
    return HTML(string=html).write_pdf()


def add_months(d: date, months: int) -> date:
    """Prideda n mėnesių, išlaikant dieną (paskutinė mėn. diena jei perpildyta)."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
