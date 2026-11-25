from django.contrib.auth.hashers import make_password
from django.db import migrations


def unusable_passwords(apps, schema_editor):
    """Programoje jungiamasi tik OTP; slaptažodžiai lieka tik /admin/ (staff)."""
    User = apps.get_model("tenancy", "User")
    for user in User.objects.filter(is_staff=False, is_superuser=False):
        user.password = make_password(None)
        user.save(update_fields=["password"])


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0008_logincode")]

    operations = [migrations.RunPython(unusable_passwords, migrations.RunPython.noop)]
