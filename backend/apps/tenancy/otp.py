import hashlib
import hmac
import logging
import secrets
import threading
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from apps.tenancy.models import LoginCode, User

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
MAX_CODES_PER_WINDOW = 3
OTP_SESSION_FLAG = "otp_login"


def _hash(code: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def find_user(email: str) -> User | None:
    return (
        User.objects.filter(email__iexact=email.strip(), is_active=True).order_by("id").first()
        if email.strip()
        else None
    )


def login_url(request) -> str:
    origins = settings.CSRF_TRUSTED_ORIGINS
    return f"{origins[0]}/login" if origins else request.build_absolute_uri("/login")


def issue_code(user: User) -> str | None:
    """Sukuria naują kodą (seni anuliuojami). None – viršytas prašymų limitas."""
    with transaction.atomic():
        User.objects.select_for_update().filter(pk=user.pk).first()
        now = timezone.now()
        recent = LoginCode.objects.filter(user=user, created_at__gte=now - CODE_TTL).count()
        if recent >= MAX_CODES_PER_WINDOW:
            return None
        LoginCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        code = f"{secrets.randbelow(1_000_000):06d}"
        LoginCode.objects.create(
            user=user,
            email=user.email.lower(),
            code_hash=_hash(code),
            expires_at=now + CODE_TTL,
        )
    return code


def send_code(user: User, code: str, request) -> None:
    """Siunčia fone, kad atsakymo trukmė neišduotų, ar paskyra egzistuoja."""
    url = login_url(request)
    if getattr(settings, "OTP_EMAIL_ASYNC", True):
        threading.Thread(target=_send_code, args=(user, code, url), daemon=True).start()
    else:
        _send_code(user, code, url)


def _code_html(code: str, url: str) -> str:
    return (
        '<div style="font-family:Arial,sans-serif;color:#111;max-width:480px">'
        '<p style="margin:0 0 8px">Jūsų prisijungimo kodas:</p>'
        '<p style="margin:0 0 16px;font-size:32px;font-weight:700;letter-spacing:6px;'
        f'font-family:Consolas,Menlo,monospace;user-select:all;-webkit-user-select:all">{code}</p>'
        '<p style="margin:0 0 8px;color:#555">Kodas galioja 10 min. ir tinka vieną kartą.</p>'
        f'<p style="margin:0 0 16px"><a href="{escape(url)}">{escape(url)}</a></p>'
        '<p style="margin:0;color:#888;font-size:12px">'
        "Jei prisijungti nebandėte, šį laišką ignoruokite.</p></div>"
    )


def _send_code(user: User, code: str, url: str) -> None:
    try:
        send_mail(
            subject=f"Prisijungimo kodas: {code}",
            message=(
                f"Jūsų prisijungimo kodas: {code}\n\n"
                f"Kodas galioja 10 min. ir tinka vieną kartą.\n{url}\n\n"
                "Jei prisijungti nebandėte, šį laišką ignoruokite."
            ),
            html_message=_code_html(code, url),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception:  # noqa: BLE001 - atsakymas vartotojui turi būti vienodas
        logger.exception("Login code email to user %s failed", user.pk)


def verify_code(user: User, code: str) -> bool:
    with transaction.atomic():
        now = timezone.now()
        lc = (
            LoginCode.objects.select_for_update()
            .filter(user=user, email__iexact=user.email, used_at__isnull=True, expires_at__gt=now)
            .first()
        )
        if lc is None:
            return False
        lc.attempts += 1
        ok = hmac.compare_digest(lc.code_hash, _hash(code.strip()))
        if ok or lc.attempts >= MAX_ATTEMPTS:
            lc.used_at = now
        lc.save(update_fields=["attempts", "used_at"])
    return ok


def send_invite(user: User, tenant_name: str, invited_by: User, request) -> None:
    try:
        send_mail(
            subject=f"Kvietimas į veiklą „{tenant_name}“ – IDV apskaita",
            message=(
                f"{invited_by.email or invited_by.username} pakvietė jus tvarkyti veiklą "
                f"„{tenant_name}“ IDV apskaitoje.\n\n"
                f"Prisijunkite su šiuo el. pašto adresu – kodą gausite laišku:\n"
                f"{login_url(request)}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
    except Exception:  # noqa: BLE001
        logger.exception("Invite email to user %s failed", user.pk)
