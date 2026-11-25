import logging
from email.headerregistry import Address

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.utils import timezone
from django_q.tasks import async_task

from apps.mailer.models import EmailOutbox
from apps.mailer.validators import ensure_public_smtp_host

logger = logging.getLogger(__name__)


def _sender(name: str, address: str) -> str:
    if not name or "<" in address:
        return address
    return str(Address(display_name=name, addr_spec=address))


def queue_email(outbox: EmailOutbox) -> None:
    async_task("apps.mailer.tasks.process_outbox")


def process_outbox() -> dict:
    """Išsiunčia laukiančius laiškus per-tenant SMTP arba sistemos SMTP; kviečiama iš qcluster."""
    sent = failed = 0
    pending = EmailOutbox.objects.filter(status=EmailOutbox.Status.PENDING).select_related("tenant")
    for msg in pending:
        tenant_smtp = getattr(msg.tenant, "smtp_settings", None)
        smtp = tenant_smtp if tenant_smtp and tenant_smtp.host else None
        if smtp is None and not settings.EMAIL_HOST:
            msg.status = EmailOutbox.Status.FAILED
            msg.error = "SMTP nustatymai nesukonfigūruoti"
            msg.save(update_fields=["status", "error"])
            failed += 1
            continue
        try:
            if smtp is not None:
                ensure_public_smtp_host(smtp.host, smtp.port)
                conn = get_connection(
                    host=smtp.host,
                    port=smtp.port,
                    username=smtp.username or "",
                    password=smtp.password or "",
                    use_tls=smtp.use_tls,
                    use_ssl=smtp.use_ssl,
                    timeout=30,
                )
                from_email = smtp.from_email or smtp.username
                from_name = smtp.from_name
                reply_to: list[str] = []
            else:
                conn = get_connection()
                from_email = settings.DEFAULT_FROM_EMAIL
                profile = getattr(msg.tenant, "profile", None)
                from_name = profile.seller_name if profile else ""
                reply_to = [profile.email] if profile and profile.email else []
            email = EmailMessage(
                subject=msg.subject,
                body=msg.body,
                from_email=_sender(from_name, from_email),
                to=[msg.to_email],
                reply_to=reply_to,
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
