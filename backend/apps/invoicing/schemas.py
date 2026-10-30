from datetime import date
from decimal import Decimal

from ninja import Schema

from apps.invoicing.models import Invoice, Payment


class ClientIn(Schema):
    name: str
    code: str = ""
    vat_code: str = ""
    email: str = ""
    address: str = ""


class ClientOut(ClientIn):
    id: int


class InvoiceLineIn(Schema):
    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "vnt."
    unit_price: Decimal


class InvoiceLineOut(InvoiceLineIn):
    id: int
    total: Decimal


class InvoiceIn(Schema):
    client_id: int
    due_date: date | None = None
    notes: str = ""
    lines: list[InvoiceLineIn]


class PaymentIn(Schema):
    amount: Decimal
    paid_at: date
    method: Payment.Method = Payment.Method.BANK
    note: str = ""


class PaymentOut(PaymentIn):
    id: int


class IssueIn(Schema):
    issue_date: date | None = None
    due_date: date | None = None
    series: str | None = None


class InvoiceOut(Schema):
    id: int
    client: ClientOut
    series: str
    year: int | None
    number: int | None
    full_number: str | None
    issue_date: date | None
    due_date: date | None
    currency: str
    status: Invoice.Status
    notes: str
    total: Decimal
    paid_total: Decimal
    lines: list[InvoiceLineOut]
    payments: list[PaymentOut]
