from datetime import date
from decimal import Decimal

from ninja import Schema

from apps.invoicing.schemas import ContactOut
from apps.purchases.models import Purchase, PurchasePayment


class PurchaseLineIn(Schema):
    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "vnt."
    unit_price: Decimal


class PurchaseLineOut(PurchaseLineIn):
    id: int
    total: Decimal


class PurchaseIn(Schema):
    supplier_id: int
    doc_number: str = ""
    document_date: date
    due_date: date | None = None
    currency: Purchase.Currency = Purchase.Currency.EUR
    exchange_rate: Decimal = Decimal("1")
    category_id: int | None = None
    deductible: bool = True
    notes: str = ""
    lines: list[PurchaseLineIn]


class PurchasePaymentIn(Schema):
    amount_original: Decimal
    exchange_rate: Decimal | None = None  # None -> pirkinio kursas
    paid_at: date
    method: PurchasePayment.Method = PurchasePayment.Method.BANK
    doc_type: PurchasePayment.DocType = PurchasePayment.DocType.NONE
    doc_number: str = ""
    note: str = ""


class PurchasePaymentOut(Schema):
    id: int
    amount_original: Decimal
    exchange_rate: Decimal
    amount_eur: Decimal
    paid_at: date
    method: PurchasePayment.Method
    doc_type: PurchasePayment.DocType
    doc_number: str
    note: str


class PurchaseOut(Schema):
    id: int
    supplier: ContactOut
    doc_number: str
    document_date: date
    due_date: date | None
    currency: str
    exchange_rate: Decimal
    status: Purchase.Status
    category_id: int | None
    deductible: bool
    notes: str
    total: Decimal
    total_eur: Decimal
    paid_total: Decimal
    lines: list[PurchaseLineOut]
    payments: list[PurchasePaymentOut]
