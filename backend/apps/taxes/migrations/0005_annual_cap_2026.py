from decimal import Decimal

from django.db import migrations


def seed(apps, schema_editor):
    TaxRule = apps.get_model("taxes", "TaxRule")
    # Oficialus 2026 lubų pagrindas: 43 x VDU = 99 422,45 (Sodra)
    TaxRule.objects.filter(year=2026).update(annual_cap=Decimal("99422.45"))


def unseed(apps, schema_editor):
    TaxRule = apps.get_model("taxes", "TaxRule")
    TaxRule.objects.filter(year=2026).update(annual_cap=Decimal("102000"))


class Migration(migrations.Migration):
    dependencies = [("taxes", "0004_gpm_2025_formula")]
    operations = [migrations.RunPython(seed, unseed)]
