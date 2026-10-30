from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.invoicing.models import Invoice
from apps.ledger.models import LedgerEntry
from apps.purchases.models import Purchase
from apps.tenancy.models import SellerProfile, Tenant


@dataclass
class JournalRow:
    date: date
    kind: str
    description: str
    counterparty: str
    amount: Decimal
    deductible: bool
    source: str


def _basis(tenant: Tenant) -> str:
    profile = getattr(tenant, "profile", None)
    if profile is None:
        return SellerProfile.AccountingBasis.CASH
    return profile.accounting_basis


def journal_rows(tenant: Tenant, year: int, month: int) -> list[JournalRow]:
    """Pajamų-išlaidų žurnalas už mėnesį pagal apskaitos principą.

    cash (pinigų): pajamos = gauti mokėjimai; išlaidos = apmokėtų dokumentų datos.
    accrual (kaupimo): pajamos = išrašytos sąskaitos; išlaidos = dokumentų datos.
    """
    cash = _basis(tenant) == SellerProfile.AccountingBasis.CASH
    rows: list[JournalRow] = []

    if cash:
        invoice_rows = (
            Invoice.objects.filter(
                tenant=tenant,
                payments__paid_at__year=year,
                payments__paid_at__month=month,
            )
            .select_related("client")
            .distinct()
        )
        for inv in invoice_rows:
            for p in inv.payments.filter(paid_at__year=year, paid_at__month=month):
                rows.append(
                    JournalRow(
                        date=p.paid_at,
                        kind="income",
                        description=f"Sąskaita {inv.full_number}",
                        counterparty=inv.client.name,
                        amount=p.amount,
                        deductible=False,
                        source="invoice",
                    )
                )
    else:
        for inv in Invoice.objects.filter(
            tenant=tenant,
            issue_date__year=year,
            issue_date__month=month,
            status__in=[
                Invoice.Status.ISSUED,
                Invoice.Status.PARTIALLY_PAID,
                Invoice.Status.PAID,
            ],
        ).select_related("client"):
            if inv.issue_date is None:
                continue
            rows.append(
                JournalRow(
                    date=inv.issue_date,
                    kind="income",
                    description=f"Sąskaita {inv.full_number}",
                    counterparty=inv.client.name,
                    amount=inv.total,
                    deductible=False,
                    source="invoice",
                )
            )

    if cash:
        purchase_rows = (
            Purchase.objects.filter(
                tenant=tenant,
                payments__paid_at__year=year,
                payments__paid_at__month=month,
            )
            .select_related("supplier")
            .distinct()
        )
        for pur in purchase_rows:
            for pp in pur.payments.filter(paid_at__year=year, paid_at__month=month):
                rows.append(
                    JournalRow(
                        date=pp.paid_at,
                        kind="expense",
                        description=f"Pirkimas {pur.doc_number}".strip(),
                        counterparty=pur.supplier.name,
                        amount=pp.amount_eur,
                        deductible=pur.deductible,
                        source="purchase",
                    )
                )
    else:
        for pur in Purchase.objects.filter(
            tenant=tenant,
            document_date__year=year,
            document_date__month=month,
            status__in=[
                Purchase.Status.RECEIVED,
                Purchase.Status.PARTIALLY_PAID,
                Purchase.Status.PAID,
            ],
        ).select_related("supplier"):
            rows.append(
                JournalRow(
                    date=pur.document_date,
                    kind="expense",
                    description=f"Pirkimas {pur.doc_number}".strip(),
                    counterparty=pur.supplier.name,
                    amount=pur.total_eur,
                    deductible=pur.deductible,
                    source="purchase",
                )
            )

    date_field = "paid_date" if cash else "document_date"
    entries = LedgerEntry.objects.filter(
        tenant=tenant,
        **{f"{date_field}__year": year, f"{date_field}__month": month},
    ).select_related("category")
    for e in entries:
        rows.append(
            JournalRow(
                date=getattr(e, date_field),
                kind=e.kind,
                description=e.description or (e.category.name if e.category else ""),
                counterparty=e.counterparty,
                amount=e.amount_eur,
                deductible=e.deductible if e.kind == LedgerEntry.Kind.EXPENSE else False,
                source="entry",
            )
        )

    rows.sort(key=lambda r: (r.date, r.kind != "income"))
    return rows


def journal_summary(rows: list[JournalRow]) -> dict:
    q = Decimal("0.01")
    income = sum((r.amount for r in rows if r.kind == "income"), Decimal("0")).quantize(q)
    expenses = sum((r.amount for r in rows if r.kind == "expense"), Decimal("0")).quantize(q)
    deductible = sum(
        (r.amount for r in rows if r.kind == "expense" and r.deductible), Decimal("0")
    ).quantize(q)
    return {
        "income_total": income,
        "expense_total": expenses,
        "deductible_total": deductible,
        "net": income - deductible,
    }
