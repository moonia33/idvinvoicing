from ninja import Schema

from apps.mailer.models import EmailOutbox


class SmtpIn(Schema):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_email: str = ""
    from_name: str = ""


class SmtpOut(Schema):
    host: str
    port: int
    username: str
    use_tls: bool
    use_ssl: bool
    from_email: str
    from_name: str
    is_configured: bool


class OutboxOut(Schema):
    id: int
    invoice_id: int | None
    to_email: str
    subject: str
    status: EmailOutbox.Status
    attempts: int
    error: str
    created_at: str
    sent_at: str | None
