from apps.invoicing.models import Invoice
from apps.mailer.models import EmailOutbox
from apps.mailer.tasks import queue_email


def default_invoice_body(number: str, payment_details: str = "") -> str:
    parts = [f"Laba,\n\nsiunčiame sąskaitą faktūrą {number}."]
    if payment_details:
        parts.append(payment_details)
    parts.append("Pagarbiai")
    return "\n\n".join(parts)


def queue_invoice_email(
    invoice: Invoice, to: str, subject: str | None = None, body: str = ""
) -> EmailOutbox:
    """Sukuria outbox įrašą su sąskaitos PDF ir užkelia siuntimą į eilę."""
    from apps.invoicing.epc import payment_details_text  # lazy – circular
    from apps.invoicing.services import generate_invoice_pdf

    pdf = generate_invoice_pdf(invoice)
    number = invoice.full_number or f"{invoice.pk}"
    outbox = EmailOutbox.objects.create(
        tenant=invoice.tenant,
        invoice=invoice,
        to_email=to,
        subject=subject or f"Sąskaita faktūra {number}",
        body=body or default_invoice_body(number, payment_details_text(invoice)),
        attachment_name=f"{number}.pdf",
        attachment=pdf,
    )
    queue_email(outbox)
    return outbox
