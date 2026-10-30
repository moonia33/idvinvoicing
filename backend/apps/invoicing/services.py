import calendar
from datetime import date, timedelta

from django.db import transaction
from django.template.loader import render_to_string

from apps.core.ltnum import lt_amount_words
from apps.core.numbering import next_document_number
from apps.invoicing.models import Invoice, Payment


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


def _cash_doc_ctx(payment: Payment) -> dict:
    """Kontekstas KPO/PPK šablonui."""
    return {
        "payment": payment,
        "title": (
            "KASOS PAJAMŲ ORDERIS"
            if payment.doc_type == Payment.DocType.KPO
            else "PINIGŲ PRIĖMIMO KVITAS"
        ),
        "amount_words": lt_amount_words(payment.amount),
    }


def cash_doc_ctxs(invoice: Invoice) -> list[dict]:
    """Sąskaitos grynųjų mokėjimų kasos dokumentai (KPO/PPK)."""
    return [
        _cash_doc_ctx(p)
        for p in invoice.payments.filter(doc_type__in=(Payment.DocType.KPO, Payment.DocType.PPK))
    ]


def generate_invoice_pdf(invoice: Invoice, with_cash_docs: bool = False) -> bytes:
    """Sugeneruoja sąskaitos PDF baitus (WeasyPrint – tik Linux/Docker aplinkoje)."""
    from weasyprint import HTML  # lazy: Windows dev be GTK bibliotekų

    tenant = invoice.tenant
    html = render_to_string(
        "invoicing/invoice_pdf.html",
        {
            "invoice": invoice,
            "profile": getattr(tenant, "profile", None),
            "cash_docs": cash_doc_ctxs(invoice) if with_cash_docs else [],
        },
    )
    return HTML(string=html).write_pdf()


def generate_cash_doc_pdf(payment: Payment) -> bytes:
    """Atskiras KPO/PPK PDF."""
    from weasyprint import HTML  # lazy

    tenant = payment.invoice.tenant
    html = render_to_string(
        "invoicing/cash_doc_pdf.html",
        {
            "d": _cash_doc_ctx(payment),
            "invoice": payment.invoice,
            "profile": getattr(tenant, "profile", None),
        },
    )
    return HTML(string=html).write_pdf()


def next_cash_doc_number(tenant, doc_type: str, year: int) -> str:
    """Grąžina KPO-2026-0001 / PPK-2026-0001 numerį (naudoja DocumentSequence)."""
    series = doc_type.upper()
    n = next_document_number(tenant, doc_type, series, year)
    return f"{series}-{year}-{n:04d}"


def add_months(d: date, months: int) -> date:
    """Prideda n mėnesių, išlaikant dieną (paskutinė mėn. diena jei perpildyta)."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
