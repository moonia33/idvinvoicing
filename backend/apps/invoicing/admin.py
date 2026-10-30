from django.contrib import admin

from apps.invoicing.models import (
    Client,
    Invoice,
    InvoiceLine,
    Payment,
    RecurringLine,
    RecurringTemplate,
)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "code", "email"]
    list_filter = ["tenant"]
    search_fields = ["name", "code"]


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["full_number", "tenant", "client", "issue_date", "status", "total"]
    list_filter = ["tenant", "status"]
    inlines = [InvoiceLineInline, PaymentInline]
    readonly_fields = ["total"]


class RecurringLineInline(admin.TabularInline):
    model = RecurringLine
    extra = 0


@admin.register(RecurringTemplate)
class RecurringTemplateAdmin(admin.ModelAdmin):
    list_display = ["client", "tenant", "frequency", "next_run_date", "active", "auto_send"]
    list_filter = ["tenant", "active", "frequency"]
    inlines = [RecurringLineInline]
