from django.db import migrations


def reencrypt(apps, schema_editor):
    """Perrašo SMTP slaptažodžius nauju DJANGO_FIELD_ENCRYPTION_KEY raktu."""
    SmtpSettings = apps.get_model("mailer", "SmtpSettings")
    for smtp in SmtpSettings.objects.exclude(password=""):
        if smtp.password:  # neiššifruotas (blogas raktas) neperrašomas tuščiu
            smtp.save(update_fields=["password"])


class Migration(migrations.Migration):
    dependencies = [("mailer", "0001_initial")]

    operations = [migrations.RunPython(reencrypt, migrations.RunPython.noop)]
