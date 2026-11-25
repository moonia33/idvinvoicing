from ninja import Router
from ninja.errors import HttpError

from apps.mailer.models import EmailOutbox, SmtpSettings
from apps.mailer.schemas import OutboxOut, SmtpIn, SmtpOut
from apps.mailer.validators import ensure_public_smtp_host
from apps.tenancy.api import current_tenant, require_owner

router = Router()


@router.get("/mail/smtp", response=SmtpOut)
def get_smtp(request):
    tenant = current_tenant(request)
    smtp = getattr(tenant, "smtp_settings", None)
    if smtp is None:
        return {
            "host": "",
            "port": 587,
            "username": "",
            "use_tls": True,
            "use_ssl": False,
            "from_email": "",
            "from_name": "",
            "is_configured": False,
        }
    return {
        "host": smtp.host,
        "port": smtp.port,
        "username": smtp.username,
        "use_tls": smtp.use_tls,
        "use_ssl": smtp.use_ssl,
        "from_email": smtp.from_email,
        "from_name": smtp.from_name,
        "is_configured": bool(smtp.host),
    }


@router.put("/mail/smtp", response=SmtpOut)
def upsert_smtp(request, data: SmtpIn):
    tenant = require_owner(request)
    if data.host:
        try:
            ensure_public_smtp_host(data.host, data.port)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from None
    defaults = data.model_dump()
    if not defaults["password"]:
        defaults.pop("password")  # tuščias slaptažodis = nepakeistas
    smtp, _ = SmtpSettings.objects.update_or_create(tenant=tenant, defaults=defaults)
    return {
        "host": smtp.host,
        "port": smtp.port,
        "username": smtp.username,
        "use_tls": smtp.use_tls,
        "use_ssl": smtp.use_ssl,
        "from_email": smtp.from_email,
        "from_name": smtp.from_name,
        "is_configured": bool(smtp.host),
    }


@router.get("/mail/outbox", response=list[OutboxOut])
def list_outbox(request, limit: int = 50):
    return EmailOutbox.objects.filter(tenant=current_tenant(request))[:limit]
