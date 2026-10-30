from django.db import models

from apps.core.fields import EncryptedCharField
from apps.tenancy.models import Tenant


class SmtpSettings(models.Model):
    """Per-tenant SMTP nustatymai sąskaitų siuntimui (DB, ne env)."""

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="smtp_settings")
    host = models.CharField(max_length=200, blank=True)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=200, blank=True)
    password = EncryptedCharField(max_length=200, blank=True)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    from_email = models.EmailField(blank=True)
    from_name = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"SMTP {self.tenant}"


class EmailOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Laukia"
        SENT = "sent", "Išsiųstas"
        FAILED = "failed", "Nepavyko"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="outbox")
    invoice = models.ForeignKey(
        "invoicing.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="emails",
    )
    to_email = models.EmailField()
    subject = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    attachment_name = models.CharField(max_length=200, blank=True)
    attachment = models.BinaryField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    MAX_ATTEMPTS = 3

    def __str__(self):
        return f"{self.to_email}: {self.subject} ({self.status})"
