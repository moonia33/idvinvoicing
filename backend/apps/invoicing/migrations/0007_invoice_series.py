from django.db import migrations, models
import django.db.models.deletion


def seed_series(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    InvoiceSeries = apps.get_model("invoicing", "InvoiceSeries")
    for tenant in Tenant.objects.all():
        if not InvoiceSeries.objects.filter(tenant=tenant).exists():
            code = getattr(getattr(tenant, "profile", None), "invoice_series", None) or "SF"
            InvoiceSeries.objects.create(tenant=tenant, code=code, is_default=True)


class Migration(migrations.Migration):
    dependencies = [
        ("invoicing", "0006_service_is_purchase_service_is_sale_and_more"),
        ("tenancy", "0007_sellerprofile_sodra_exempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvoiceSeries",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("code", models.CharField(max_length=10)),
                ("is_default", models.BooleanField(default=False)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invoice_series_set",
                        to="tenancy.tenant",
                    ),
                ),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.AddConstraint(
            model_name="invoiceseries",
            constraint=models.UniqueConstraint(
                fields=("tenant", "code"), name="unique_invoice_series_code"
            ),
        ),
        migrations.RunPython(seed_series, migrations.RunPython.noop),
    ]
