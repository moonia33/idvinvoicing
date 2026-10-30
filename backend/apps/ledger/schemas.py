from datetime import date
from decimal import Decimal

from ninja import Schema

from apps.ledger.models import Category, LedgerEntry


class CategoryIn(Schema):
    kind: Category.Kind
    name: str
    is_deductible: bool = True


class CategoryOut(CategoryIn):
    id: int


class EntryIn(Schema):
    kind: LedgerEntry.Kind
    category_id: int | None = None
    document_date: date
    paid_date: date | None = None
    counterparty: str = ""
    description: str = ""
    currency: LedgerEntry.Currency = LedgerEntry.Currency.EUR
    amount_original: Decimal
    exchange_rate: Decimal = Decimal("1")
    deductible: bool = True
    tax_kind: LedgerEntry.TaxKind = LedgerEntry.TaxKind.NONE
    tax_year: int | None = None


class EntryOut(Schema):
    id: int
    kind: LedgerEntry.Kind
    category_id: int | None
    document_date: date
    paid_date: date
    counterparty: str
    description: str
    currency: LedgerEntry.Currency
    amount_original: Decimal
    exchange_rate: Decimal
    amount_eur: Decimal
    deductible: bool
    tax_kind: LedgerEntry.TaxKind
    tax_year: int | None


class JournalRowOut(Schema):
    date: date
    kind: str
    description: str
    counterparty: str
    amount: Decimal
    deductible: bool
    source: str


class JournalOut(Schema):
    rows: list[JournalRowOut]
    income_total: Decimal
    expense_total: Decimal
    deductible_total: Decimal
    net: Decimal
