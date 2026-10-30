import logging

from django.core.mail import EmailMessage, get_connection
from django.utils import timezone
from django_q.tasks import async_task

from apps.mailer.models import EmailOutbox

logger = logging.getLogger(__name__)


def queue_email(outbox: EmailOutbox) -> None:
    async_task("apps.mailer.tasks.process_outbox")


def process_outbox() -> dict:
    """Išsiunčia laukiančius laiškus per-tenant SMTP; kviečiama iš qcluster."""
    sent = failed = 0
    pending = EmailOutbox.objects.filter(status=EmailOutbox.Status.PENDING).select_related("tenant")
    for msg in pending:
        smtp = getattr(msg.tenant, "smtp_settings", None)
        if not smtp or not smtp.host:
            msg.status = EmailOutbox.Status.FAILED
            msg.error = "SMTP nustatymai nesukonfigūruoti"
            msg.save(update_fields=["status", "error"])
            failed += 1
            continue
        try:
            conn = get_connection(
                host=smtp.host,
                port=smtp.port,
                username=smtp.username or None,
                password=smtp.password or None,
                use_tls=smtp.use_tls,
                use_ssl=smtp.use_ssl,
                timeout=30,
            )
            email = EmailMessage(
                subject=msg.subject,
                body=msg.body,
                from_email=smtp.from_email or smtp.username,
                to=[msg.to_email],
                connection=conn,
            )
            if msg.attachment:
                email.attach(
                    msg.attachment_name or "document.pdf",
                    bytes(msg.attachment),
                    "application/pdf",
                )
            email.send(fail_silently=False)
            msg.status = EmailOutbox.Status.SENT
            msg.sent_at = timezone.now()
            msg.error = ""
            sent += 1
        except Exception as exc:  # noqa: BLE001 - loguojam ir žymim
            logger.exception("Outbox %s send failed", msg.id)
            msg.attempts += 1
            msg.error = str(exc)
            if msg.attempts >= EmailOutbox.MAX_ATTEMPTS:
                msg.status = EmailOutbox.Status.FAILED
            failed += 1
        msg.save()
    return {"sent": sent, "failed": failed}
