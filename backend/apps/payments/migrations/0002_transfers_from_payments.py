from django.db import migrations


def forwards(apps, schema_editor):
    MoneyTransfer = apps.get_model("payments", "MoneyTransfer")
    Payment = apps.get_model("invoicing", "Payment")
    PurchasePayment = apps.get_model("purchases", "PurchasePayment")
    for p in Payment.objects.filter(transfer__isnull=True, amount__gt=0).select_related("invoice"):
        inv = p.invoice
        p.transfer = MoneyTransfer.objects.create(
            tenant_id=inv.tenant_id,
            direction="in",
            date=p.paid_at,
            amount=p.amount,
            currency=inv.currency,
            method=p.method,
            counterparty_id=inv.client_id,
            note=p.note,
            mirror=True,
        )
        p.save(update_fields=["transfer"])
    for p in PurchasePayment.objects.filter(
        transfer__isnull=True, amount_original__gt=0
    ).select_related("purchase"):
        pur = p.purchase
        p.transfer = MoneyTransfer.objects.create(
            tenant_id=pur.tenant_id,
            direction="out",
            date=p.paid_at,
            amount=p.amount_original,
            currency=pur.currency,
            method=p.method,
            counterparty_id=pur.supplier_id,
            note=p.note,
            mirror=True,
        )
        p.save(update_fields=["transfer"])


def backwards(apps, schema_editor):
    # Atjungiame sudengimus, kad CASCADE neištrintų pačių mokėjimų.
    apps.get_model("invoicing", "Payment").objects.update(transfer=None)
    apps.get_model("purchases", "PurchasePayment").objects.update(transfer=None)
    apps.get_model("payments", "MoneyTransfer").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("invoicing", "0008_payment_transfer"),
        ("purchases", "0004_purchasepayment_transfer"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
