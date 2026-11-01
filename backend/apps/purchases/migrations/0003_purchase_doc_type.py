from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("purchases", "0002_supplier_to_counterparty"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("sf", "Sąskaita faktūra"),
                    ("receipt", "Kasos kvitas"),
                    ("ppk", "Pirkimo-pardavimo kvitas (PPK)"),
                    ("kio", "Kasos išlaidų orderis (KIO)"),
                ],
                default="sf",
                max_length=10,
                verbose_name="Dokumento tipas",
            ),
        ),
    ]
