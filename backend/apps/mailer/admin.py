from django.contrib import admin

from apps.mailer.models import EmailOutbox, SmtpSettings


@admin.register(SmtpSettings)
class SmtpSettingsAdmin(admin.ModelAdmin):
    list_display = ["tenant", "host", "port", "from_email"]
    fields = [
        "tenant",
        "host",
        "port",
        "username",
        "password",
        "use_tls",
        "use_ssl",
        "from_email",
        "from_name",
    ]


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ["to_email", "subject", "tenant", "status", "attempts", "created_at"]
    list_filter = ["tenant", "status"]
    readonly_fields = ["attachment"]
