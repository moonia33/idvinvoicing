import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations


def reencrypt(apps, schema_editor):
    """Perrašo SMTP slaptažodžius nauju DJANGO_FIELD_ENCRYPTION_KEY raktu."""
    SmtpSettings = apps.get_model("mailer", "SmtpSettings")
    for smtp in SmtpSettings.objects.exclude(password=""):
        if smtp.password:  # neiššifruotas (blogas raktas) neperrašomas tuščiu
            smtp.save(update_fields=["password"])


def back_to_legacy(apps, schema_editor):
    """Atgal: šifruoja senu (iš SECRET_KEY) raktu, kad ankstesnė versija juos perskaitytų."""
    SmtpSettings = apps.get_model("mailer", "SmtpSettings")
    legacy = Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()))
    table = SmtpSettings._meta.db_table
    with schema_editor.connection.cursor() as cur:
        for smtp in SmtpSettings.objects.exclude(password=""):
            if smtp.password:
                token = legacy.encrypt(smtp.password.encode()).decode()
                cur.execute(f"UPDATE {table} SET password = %s WHERE id = %s", [token, smtp.pk])


class Migration(migrations.Migration):
    dependencies = [("mailer", "0001_initial")]

    operations = [migrations.RunPython(reencrypt, back_to_legacy)]
