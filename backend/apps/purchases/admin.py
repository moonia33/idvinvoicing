from django.contrib import admin

from apps.purchases.models import Purchase, PurchaseLine, PurchasePayment, Supplier


class PurchaseLineInline(admin.TabularInline):
    model = PurchaseLine
    extra = 0


class PurchasePaymentInline(admin.TabularInline):
    model = PurchasePayment
    extra = 0
    readonly_fields = ("amount_eur",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "vat_code", "tenant")
    list_filter = ("tenant",)
    search_fields = ("name", "code")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("supplier", "doc_number", "document_date", "status", "total", "tenant")
    list_filter = ("tenant", "status", "currency")
    search_fields = ("doc_number", "supplier__name")
    inlines = [PurchaseLineInline, PurchasePaymentInline]
