from decimal import Decimal

from django.db import migrations

# 2025+ GPM modelis: 5% iki 20 000 AP, progresyviai iki 20% ties 42 500 AP, 20% virš.
# 2026 m.: MMA 1153 (min. PSD 80,48/mėn., min. VSD 144,36/mėn.), VSD pensijai 15,52%.
BASE = {
    "gpm_rate": Decimal("0.05"),
    "gpm_flat_cap": Decimal("20000"),
    "gpm_progressive_cap": Decimal("42500"),
    "gpm_top_rate": Decimal("0.20"),
    "fixed_deduction_rate": Decimal("0.30"),
    "social_base_share": Decimal("0.90"),
    "vsd_rate": Decimal("0.1252"),
    "vsd_rate_pension": Decimal("0.1552"),
    "psd_rate": Decimal("0.0698"),
}


def seed(apps, schema_editor):
    TaxRule = apps.get_model("taxes", "TaxRule")
    TaxRule.objects.update_or_create(
        year=2025, defaults={**BASE, "mma_monthly": Decimal("1038"), "annual_cap": Decimal("96264")}
    )
    TaxRule.objects.update_or_create(
        year=2026,
        defaults={
            **BASE,
            "mma_monthly": Decimal("1153"),
            "annual_cap": Decimal("102000"),  # ~43 x VDU, apytiksliai – tikslinti per admin
        },
    )


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("taxes", "0003_remove_taxrule_gpm_reduction_coef_and_more"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
