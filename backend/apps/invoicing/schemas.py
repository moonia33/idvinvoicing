from datetime import date
from decimal import Decimal

from ninja import Schema

from apps.invoicing.models import Invoice, Payment, RecurringTemplate


class ContactIn(Schema):
    name: str
    code: str = ""
    vat_code: str = ""
    email: str = ""
    address: str = ""
    is_client: bool = False
    is_supplier: bool = False


class ContactOut(ContactIn):
    id: int


class ServiceIn(Schema):
    code: str = ""
    name: str
    category_id: int | None = None
    unit: str = "vnt."
    unit_price: Decimal
    is_sale: bool = True
    is_purchase: bool = False
    active: bool = True


class ServiceOut(ServiceIn):
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
    doc_type: Payment.DocType = Payment.DocType.NONE
    doc_number: str = ""
    note: str = ""


class PaymentOut(PaymentIn):
    id: int


class IssueIn(Schema):
    issue_date: date | None = None
    due_date: date | None = None
    series: str | None = None


class InvoiceOut(Schema):
    id: int
    client: ContactOut
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


class SendIn(Schema):
    to: str | None = None
    subject: str | None = None
    body: str = ""


class RecurringIn(Schema):
    client_id: int
    series: str = "SF"
    frequency: RecurringTemplate.Frequency
    next_run_date: date
    end_date: date | None = None
    active: bool = True
    auto_send: bool = False
    email_to: str = ""
    notes: str = ""
    lines: list[InvoiceLineIn]


class RecurringOut(Schema):
    id: int
    client: ContactOut
    series: str
    frequency: RecurringTemplate.Frequency
    next_run_date: date
    end_date: date | None
    active: bool
    auto_send: bool
    email_to: str
    notes: str
    lines: list[InvoiceLineOut]
