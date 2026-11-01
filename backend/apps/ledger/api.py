from django.shortcuts import get_object_or_404
from ninja import Router, Status
from ninja.errors import HttpError

from apps.ledger.models import Category, LedgerEntry
from apps.ledger.schemas import (
    CategoryIn,
    CategoryOut,
    EntryIn,
    EntryOut,
    JournalOut,
)
from apps.ledger.services import journal_rows, journal_summary
from apps.tenancy.api import current_tenant

router = Router()


def get_category(tenant, category_id: int) -> Category:
    return get_object_or_404(Category, id=category_id, tenant=tenant)


def get_entry(tenant, entry_id: int) -> LedgerEntry:
    return get_object_or_404(LedgerEntry, id=entry_id, tenant=tenant)


# --- Categories ---


@router.get("/ledger/categories", response=list[CategoryOut])
def list_categories(request, kind: str | None = None):
    qs = Category.objects.filter(tenant=current_tenant(request))
    if kind:
        qs = qs.filter(kind=kind)
    return qs


@router.post("/ledger/categories", response={201: CategoryOut})
def create_category(request, data: CategoryIn):
    cat, created = Category.objects.get_or_create(
        tenant=current_tenant(request),
        kind=data.kind,
        name=data.name,
        defaults={"is_deductible": data.is_deductible},
    )
    return Status(201 if created else 200, cat)


@router.put("/ledger/categories/{category_id}", response=CategoryOut)
def update_category(request, category_id: int, data: CategoryIn):
    cat = get_category(current_tenant(request), category_id)
    for key, value in data.model_dump().items():
        setattr(cat, key, value)
    cat.save()
    return cat


@router.delete("/ledger/categories/{category_id}", response={204: None})
def delete_category(request, category_id: int):
    get_category(current_tenant(request), category_id).delete()
    return Status(204, None)


# --- Entries ---


def _entry_defaults(tenant, data: EntryIn) -> dict:
    values = data.model_dump()
    category_id = values.pop("category_id")
    values["category"] = get_category(tenant, category_id) if category_id else None
    if values["paid_date"] is None:
        values["paid_date"] = values["document_date"]
    return values


@router.get("/ledger/entries", response=list[EntryOut])
def list_entries(request, kind: str | None = None, year: int | None = None):
    qs = LedgerEntry.objects.filter(tenant=current_tenant(request)).select_related("category")
    if kind:
        qs = qs.filter(kind=kind)
    if year:
        qs = qs.filter(document_date__year=year)
    return qs


@router.post("/ledger/entries", response={201: EntryOut})
def create_entry(request, data: EntryIn):
    tenant = current_tenant(request)
    entry = LedgerEntry.objects.create(tenant=tenant, **_entry_defaults(tenant, data))
    return Status(201, entry)


@router.put("/ledger/entries/{entry_id}", response=EntryOut)
def update_entry(request, entry_id: int, data: EntryIn):
    tenant = current_tenant(request)
    entry = get_entry(tenant, entry_id)
    for key, value in _entry_defaults(tenant, data).items():
        setattr(entry, key, value)
    entry.save()
    return entry


@router.delete("/ledger/entries/{entry_id}", response={204: None})
def delete_entry(request, entry_id: int):
    get_entry(current_tenant(request), entry_id).delete()
    return Status(204, None)


# --- Journal ---


@router.get("/ledger/journal", response=JournalOut)
def journal(request, year: int, month: int):
    if not 0 <= month <= 12:
        raise HttpError(400, "Neteisingas mėnuo")
    tenant = current_tenant(request)
    if month == 0:
        rows = [r for m in range(1, 13) for r in journal_rows(tenant, year, m)]
    else:
        rows = journal_rows(tenant, year, month)
    return {"rows": rows, **journal_summary(rows)}
