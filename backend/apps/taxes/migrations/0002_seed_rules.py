from decimal import Decimal

from django.db import migrations

# 2025 m. IV tarifai (apytiksliai – verifikuoti su VMI/Sodra ir koreguoti per admin):
# VSD 12,52%, PSD 6,98% nuo 90% pelno; MMA 1038; metinė lubų bazė 43 x VDU ≈ 96264;
# GPM lengvatinė formulė pelnui < 35 000; leidžiami atskaitymai 30%.
RULES_2025 = {
    "year": 2025,
    "gpm_rate": Decimal("0.15"),
    "gpm_soft_cap": Decimal("35000"),
    "gpm_reduction_coef": Decimal("0.10"),
    "fixed_deduction_rate": Decimal("0.30"),
    "social_base_share": Decimal("0.90"),
    "vsd_rate": Decimal("0.1252"),
    "psd_rate": Decimal("0.0698"),
    "mma_monthly": Decimal("1038"),
    "annual_cap": Decimal("96264"),
}


def seed(apps, schema_editor):
    TaxRule = apps.get_model("taxes", "TaxRule")
    TaxRule.objects.get_or_create(year=2025, defaults={k: v for k, v in RULES_2025.items() if k != "year"})
    TaxRule.objects.get_or_create(
        year=2026,
        defaults={k: v for k, v in RULES_2025.items() if k != "year"},
    )


def unseed(apps, schema_editor):
    TaxRule = apps.get_model("taxes", "TaxRule")
    TaxRule.objects.filter(year__in=[2025, 2026]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("taxes", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
