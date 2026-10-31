import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("invoicing", "0005_payment_doc_number_payment_doc_type_and_more"),
        ("ledger", "0002_ledgerentry_tax_kind_ledgerentry_tax_year"),
        ("tenancy", "0005_sellerprofile_activity_start"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="is_purchase",
            field=models.BooleanField(default=False, verbose_name="Pirkimams"),
        ),
        migrations.AddField(
            model_name="service",
            name="is_sale",
            field=models.BooleanField(default=True, verbose_name="Pardavimams"),
        ),
        migrations.AlterField(
            model_name="service",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="services",
                to="ledger.category",
            ),
        ),
        # Client -> Counterparty: ta pati lentelė, duomenys išsaugomi
        migrations.RenameModel(old_name="Client", new_name="Counterparty"),
        migrations.AlterField(
            model_name="counterparty",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="counterparties",
                to="tenancy.tenant",
            ),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="is_client",
            field=models.BooleanField(default=True, verbose_name="Klientas"),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="is_supplier",
            field=models.BooleanField(default=False, verbose_name="Tiekėjas"),
        ),
    ]
