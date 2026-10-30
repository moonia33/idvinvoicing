from apps.invoicing.models import Invoice
from apps.mailer.models import EmailOutbox
from apps.mailer.tasks import queue_email


def queue_invoice_email(
    invoice: Invoice, to: str, subject: str | None = None, body: str = ""
) -> EmailOutbox:
    """Sukuria outbox įrašą su sąskaitos PDF ir užkelia siuntimą į eilę."""
    from apps.invoicing.services import generate_invoice_pdf  # lazy – circular

    pdf = generate_invoice_pdf(invoice)
    number = invoice.full_number or f"{invoice.pk}"
    outbox = EmailOutbox.objects.create(
        tenant=invoice.tenant,
        invoice=invoice,
        to_email=to,
        subject=subject or f"Sąskaita faktūra {number}",
        body=body or f"Laba,\n\nsiunčiame sąskaitą faktūrą {number}.\n\nPagarbiai",
        attachment_name=f"{number}.pdf",
        attachment=pdf,
    )
    queue_email(outbox)
    return outbox
