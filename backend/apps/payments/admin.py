from django.contrib import admin

from apps.payments.models import MoneyTransfer


@admin.register(MoneyTransfer)
class MoneyTransferAdmin(admin.ModelAdmin):
    list_display = ("date", "direction", "amount", "currency", "counterparty_name", "tenant")
    list_filter = ("direction", "source", "ignored")
    search_fields = ("counterparty_name", "reference", "external_id")
