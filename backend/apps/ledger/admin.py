from django.contrib import admin

from apps.ledger.models import Category, LedgerEntry


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "kind", "is_deductible"]
    list_filter = ["tenant", "kind"]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ["document_date", "tenant", "kind", "amount_eur", "currency", "deductible"]
    list_filter = ["tenant", "kind", "currency", "deductible"]
    readonly_fields = ["amount_eur"]
