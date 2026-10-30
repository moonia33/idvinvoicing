from django.db import migrations


def create_schedules(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.get_or_create(
        func="apps.invoicing.tasks.generate_recurring_invoices",
        defaults={"name": "recurring-invoices", "schedule_type": "D"},
    )
    Schedule.objects.get_or_create(
        func="apps.mailer.tasks.process_outbox",
        defaults={"name": "email-outbox", "schedule_type": "I", "minutes": 15},
    )


def remove_schedules(apps, schema_editor):
    Schedule = apps.get_model("django_q", "Schedule")
    Schedule.objects.filter(
        func__in=[
            "apps.invoicing.tasks.generate_recurring_invoices",
            "apps.mailer.tasks.process_outbox",
        ]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("invoicing", "0002_recurringtemplate_recurringline"),
        ("django_q", "0019_alter_task_options_alter_ormq_key_alter_ormq_lock_and_more"),
    ]

    operations = [migrations.RunPython(create_schedules, remove_schedules)]
