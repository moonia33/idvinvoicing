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
    doc_number: str = Field(default="", max_length=40)
    ignored: bool = False


class TransferIn(TransferUpdateIn):
    direction: MoneyTransfer.Direction
    currency: MoneyTransfer.Currency = MoneyTransfer.Currency.EUR
    doc_type: MoneyTransfer.DocType = MoneyTransfer.DocType.NONE
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
    doc_type: str
    doc_number: str
    account_iban: str
    bank_import_id: int | None
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


class ImportStatementOut(Schema):
    account_iban: str
    currency: str
    bank_name: str
    owner_name: str
    period_from: dt.date | None
    period_to: dt.date | None
    entries: int
    skipped: int


class ImportEntryOut(Schema):
    account_iban: str
    external_id: str
    direction: str
    date: dt.date
    amount: Decimal
    currency: str
    method: str
    counterparty_name: str
    counterparty_iban: str
    counterparty_code: str
    counterparty_id: int | None
    reference: str
    bank_code: str
    own_transfer: bool
    duplicate: bool
    supported: bool


class ImportResultOut(Schema):
    statements: list[ImportStatementOut]
    entries: list[ImportEntryOut]
    new_count: int
    duplicate_count: int
    unsupported_count: int
    created_count: int = 0
