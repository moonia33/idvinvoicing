from django.template.loader import render_to_string

from apps.core.ltnum import lt_amount_words
from apps.core.numbering import next_document_number
from apps.purchases.models import PurchasePayment


def next_kio_number(tenant, year: int) -> str:
    """Grąžina KIO-2026-0001 numerį (ta pati DocumentSequence infrastruktūra)."""
    n = next_document_number(tenant, "kio", "KIO", year)
    return f"KIO-{year}-{n:04d}"


def generate_kio_pdf(payment: PurchasePayment) -> bytes:
    """Atskiras KIO (kasos išlaidų orderio) PDF."""
    from weasyprint import HTML  # lazy: Windows dev be GTK bibliotekų

    purchase = payment.purchase
    html = render_to_string(
        "purchases/kio_pdf.html",
        {
            "payment": payment,
            "purchase": purchase,
            "amount_words": lt_amount_words(payment.amount_eur),
            "profile": getattr(purchase.tenant, "profile", None),
        },
    )
    return HTML(string=html).write_pdf()
