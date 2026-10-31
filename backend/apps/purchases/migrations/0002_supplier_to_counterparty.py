import django.db.models.deletion
from django.db import migrations, models


def copy_suppliers_to_counterparties(apps, schema_editor):
    """Supplier -> Counterparty(is_supplier=True), Purchase.supplier_id peradresuojamas."""
    Supplier = apps.get_model("purchases", "Supplier")
    Counterparty = apps.get_model("invoicing", "Counterparty")
    Purchase = apps.get_model("purchases", "Purchase")
    for s in Supplier.objects.all():
        cp = Counterparty.objects.create(
            tenant_id=s.tenant_id,
            name=s.name,
            code=s.code,
            vat_code=s.vat_code,
            email=s.email,
            address=s.address,
            is_client=False,
            is_supplier=True,
        )
        Purchase.objects.filter(supplier_id=s.id).update(supplier_id=cp.id)


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0001_initial"),
        ("invoicing", "0006_service_is_purchase_service_is_sale_and_more"),
    ]

    operations = [
        migrations.RunPython(copy_suppliers_to_counterparties, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="purchase",
            name="supplier",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchases",
                to="invoicing.counterparty",
            ),
        ),
        migrations.DeleteModel(name="Supplier"),
    ]
