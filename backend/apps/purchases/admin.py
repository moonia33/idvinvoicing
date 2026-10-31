from django.contrib import admin

from apps.purchases.models import Purchase, PurchaseLine, PurchasePayment


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


class PurchasePaymentInline(admin.TabularInline):
    model = PurchasePayment
    extra = 0
    readonly_fields = ("amount_eur",)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("supplier", "doc_number", "document_date", "status", "total", "tenant")
    list_filter = ("tenant", "status", "currency")
    search_fields = ("doc_number", "supplier__name")
    inlines = [PurchaseLineInline, PurchasePaymentInline]
