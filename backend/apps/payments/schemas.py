import datetime as dt
from decimal import Decimal

from ninja import Field, Schema

from apps.payments.models import MoneyTransfer


class AllocationIn(Schema):
    invoice_id: int | None = None
    purchase_id: int | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=6)


class TransferUpdateIn(Schema):
    date: dt.date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: MoneyTransfer.Method = MoneyTransfer.Method.BANK
    counterparty_id: int | None = None
    counterparty_name: str = Field(default="", max_length=200)
    counterparty_iban: str = Field(default="", max_length=34)
    reference: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=200)
    ignored: bool = False


class TransferIn(TransferUpdateIn):
    direction: MoneyTransfer.Direction
    currency: MoneyTransfer.Currency = MoneyTransfer.Currency.EUR
    doc_type: str = Field(default="", max_length=4)
    allocations: list[AllocationIn] = []


class AllocationOut(Schema):
    id: int
    kind: str  # invoice | purchase
    document_id: int
    document_label: str
    amount: Decimal  # mokėjimo valiuta
    doc_type: str
    doc_number: str


class TransferOut(Schema):
    id: int
    direction: MoneyTransfer.Direction
    date: dt.date
    amount: Decimal
    currency: str
    method: MoneyTransfer.Method
    counterparty_id: int | None
    counterparty_display: str
    counterparty_name: str
    counterparty_iban: str
    reference: str
    note: str
    ignored: bool
    source: MoneyTransfer.Source
    status: MoneyTransfer.Status
    allocated_total: Decimal
    unallocated: Decimal
    allocations: list[AllocationOut]


class OpenDocumentOut(Schema):
    kind: str
    id: int
    label: str
    counterparty_id: int
    counterparty_name: str
    date: dt.date
    due_date: dt.date | None
    currency: str
    total: Decimal
    remaining: Decimal
