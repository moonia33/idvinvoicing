"""EPC069-12 (SEPA Credit Transfer) mokėjimo QR kodas sąskaitai."""

import re
from dataclasses import dataclass
from decimal import Decimal

import segno

from apps.invoicing.models import Invoice

PAYABLE_STATUSES = (Invoice.Status.ISSUED, Invoice.Status.PARTIALLY_PAID)


@dataclass
class PaymentQr:
    name: str
    iban: str
    amount: Decimal
    reference: str
    payload: str

    @property
    def svg_data_uri(self) -> str:
        return segno.make(self.payload, error="m", micro=False, encoding="utf-8").svg_data_uri(
            scale=4, border=2
        )


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def valid_iban(iban: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", iban):
        return False
    digits = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def format_iban(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def payment_qr(invoice: Invoice) -> PaymentQr | None:
    """QR tik išrašytai, neapmokėtai EUR sąskaitai, kai pardavėjas turi galiojantį IBAN."""
    profile = getattr(invoice.tenant, "profile", None)
    if profile is None or invoice.currency != "EUR" or invoice.status not in PAYABLE_STATUSES:
        return None
    iban = normalize_iban(profile.iban)
    if not valid_iban(iban):
        return None
    amount = invoice.total - invoice.paid_total
    if amount < Decimal("0.01") or amount > Decimal("999999999.99"):
        return None
    name = " ".join(profile.seller_name.split())[:70]
    reference = invoice.full_number or ""
    if not name or not reference:
        return None
    payload = "\n".join(
        ["BCD", "002", "1", "SCT", "", name, iban, f"EUR{amount:.2f}", "", "", reference]
    )
    return PaymentQr(name=name, iban=iban, amount=amount, reference=reference, payload=payload)


def payment_details_text(invoice: Invoice) -> str:
    qr = payment_qr(invoice)
    if qr is None:
        return ""
    return (
        "Mokėjimo rekvizitai:\n"
        f"Gavėjas: {qr.name}\n"
        f"IBAN: {format_iban(qr.iban)}\n"
        f"Suma: {qr.amount:.2f} EUR\n"
        f"Mokėjimo paskirtis: {qr.reference}\n\n"
        "Sąskaitos PDF yra mokėjimo QR kodas – nuskenuokite jį banko programėle."
    )
