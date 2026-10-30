from django.contrib import admin

from apps.taxes.models import TaxRule


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = [
        "year",
        "gpm_rate",
        "vsd_rate",
        "psd_rate",
        "mma_monthly",
        "annual_cap",
    ]
