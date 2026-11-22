import pytest
from django.core.mail import get_connection as real_get_connection

from apps.mailer.models import EmailOutbox, SmtpSettings
from apps.mailer.tasks import process_outbox
from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def locmem_connection(**kwargs):
    return real_get_connection(backend="django.core.mail.backends.locmem.EmailBackend")


def test_smtp_upsert_and_password_encrypted(api_client, tenant):
    resp = api_client.put(
        "/api/v1/mail/smtp",
        {
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "u@x.lt",
            "password": "secret1",
            "from_email": "u@x.lt",
        },
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["is_configured"] is True
    assert "password" not in resp.json()

    smtp = SmtpSettings.objects.get(tenant=tenant)
    assert smtp.password == "secret1"  # per ORM – iššifruota
    # ORM reikšmė jau iššifruota – tikriname kad DB nėra plaintext
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT password FROM mailer_smtpsettings")
        (raw_db,) = cur.fetchone()
    assert raw_db != "secret1"


def test_invoice_send_queues_outbox(api_client, monkeypatch):
    monkeypatch.setattr("apps.invoicing.services.generate_invoice_pdf", lambda inv: b"%PDF-1.4")
    cid = post_json(api_client, "/api/v1/clients", {"name": "K", "email": "k@x.lt"}).json()["id"]
    inv = post_json(
        api_client,
        "/api/v1/invoices",
        {"client_id": cid, "lines": [{"description": "x", "unit_price": "10.00"}]},
    ).json()
    post_json(api_client, f"/api/v1/invoices/{inv['id']}/issue", {})

    resp = post_json(api_client, f"/api/v1/invoices/{inv['id']}/send", {})
    assert resp.status_code == 200
    msg = EmailOutbox.objects.get()
    assert msg.to_email == "k@x.lt"
    assert msg.attachment_name.startswith("SF-")
    assert msg.status == "pending"


def test_process_outbox_sent(api_client, tenant, monkeypatch):
    monkeypatch.setattr("apps.mailer.tasks.get_connection", locmem_connection)
    api_client.put(
        "/api/v1/mail/smtp",
        {"host": "smtp.x.lt", "username": "u", "from_email": "u@x.lt"},
        content_type="application/json",
    )
    EmailOutbox.objects.create(
        tenant=tenant,
        to_email="a@b.lt",
        subject="Test",
        attachment=b"%PDF",
        attachment_name="inv.pdf",
    )
    result = process_outbox()
    assert result == {"sent": 1, "failed": 0}
    assert EmailOutbox.objects.get().status == "sent"


def test_process_outbox_no_smtp(tenant):
    EmailOutbox.objects.create(tenant=tenant, to_email="a@b.lt", subject="Test")
    process_outbox()
    msg = EmailOutbox.objects.get()
    assert msg.status == "failed"
    assert "SMTP" in msg.error


def test_process_outbox_falls_back_to_system_smtp(tenant, settings, monkeypatch):
    from django.core import mail

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.EMAIL_HOST = "smtp.system.lt"
    settings.DEFAULT_FROM_EMAIL = "apskaita@system.lt"
    tenant.profile.email = "seller@x.lt"
    tenant.profile.save()
    EmailOutbox.objects.create(tenant=tenant, to_email="a@b.lt", subject="Test")

    assert process_outbox() == {"sent": 1, "failed": 0}
    sent = mail.outbox[0]
    assert sent.from_email.endswith("<apskaita@system.lt>")
    assert tenant.profile.seller_name in sent.from_email
    assert sent.reply_to == ["seller@x.lt"]


def test_process_outbox_tenant_smtp_has_priority(api_client, tenant, settings, monkeypatch):
    monkeypatch.setattr("apps.mailer.tasks.get_connection", locmem_connection)
    settings.EMAIL_HOST = "smtp.system.lt"
    api_client.put(
        "/api/v1/mail/smtp",
        {"host": "smtp.x.lt", "username": "u", "from_email": "u@x.lt", "from_name": "Jonas"},
        content_type="application/json",
    )
    EmailOutbox.objects.create(tenant=tenant, to_email="a@b.lt", subject="Test")

    process_outbox()
    from django.core import mail

    assert mail.outbox[0].from_email == "Jonas <u@x.lt>"
    assert mail.outbox[0].reply_to == []


def test_tenant_smtp_without_username_does_not_reuse_system_credentials(
    api_client, tenant, settings, monkeypatch
):
    captured: dict = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return locmem_connection()

    monkeypatch.setattr("apps.mailer.tasks.get_connection", capture)
    settings.EMAIL_HOST_USER = "system@x.lt"
    settings.EMAIL_HOST_PASSWORD = "system-secret"
    api_client.put(
        "/api/v1/mail/smtp",
        {"host": "smtp.tenant.lt", "from_email": "t@x.lt"},
        content_type="application/json",
    )
    EmailOutbox.objects.create(tenant=tenant, to_email="a@b.lt", subject="Test")

    assert process_outbox() == {"sent": 1, "failed": 0}
    assert captured["username"] == ""
    assert captured["password"] == ""


@pytest.mark.parametrize(
    ("name", "address", "expected"),
    [
        ("Jonas, UAB", "u@x.lt", '"Jonas, UAB" <u@x.lt>'),
        ("Jonas", "App <u@x.lt>", "App <u@x.lt>"),
        ("Jonas", "u@žvejyba.lt", "Jonas <u@žvejyba.lt>"),
        ("", "u@x.lt", "u@x.lt"),
    ],
)
def test_sender_formatting(name, address, expected):
    from apps.mailer.tasks import _sender

    assert _sender(name, address) == expected
