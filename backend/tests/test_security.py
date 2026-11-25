import socket
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from openpyxl import load_workbook

from apps.core import fields
from apps.core.pdf import _data_only_fetcher
from apps.mailer.models import SmtpSettings
from apps.mailer.validators import ensure_public_smtp_host
from apps.reports.services import _neutralize_formulas
from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def _resolve_to(monkeypatch, ip: str):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, 1, 6, "", (ip, 0))]
    )


# --- prisijungimo ribojimas (django-axes) ---


def test_login_locked_after_failures(client, user, settings):
    settings.AXES_FAILURE_LIMIT = 3
    for _ in range(3):
        post_json(client, "/api/v1/auth/login", {"username": "tomas", "password": "blogai"})
    resp = post_json(client, "/api/v1/auth/login", {"username": "tomas", "password": "slaptas123"})
    assert resp.status_code == 429


# --- API dokumentacija ---


def test_api_docs_flags_follow_debug():
    import importlib

    from django.conf import settings

    import config.api

    importlib.reload(config.api)
    assert (config.api.api.docs_url is None) is (not settings.DEBUG)


# --- slaptažodžio keitimas ---


def test_password_change_requires_12_chars(api_client):
    resp = post_json(
        api_client,
        "/api/v1/auth/password",
        {"old_password": "slaptas123", "new_password": "Trumpas12!"},
    )
    assert resp.status_code == 400
    resp = post_json(
        api_client,
        "/api/v1/auth/password",
        {"old_password": "slaptas123", "new_password": "ilgas-Slaptazodis-2026"},
    )
    assert resp.status_code == 200


# --- SMTP SSRF ---


def test_smtp_private_host_rejected(api_client, monkeypatch):
    _resolve_to(monkeypatch, "10.0.0.5")
    resp = api_client.put(
        "/api/v1/mail/smtp",
        {"host": "internal.example", "port": 587},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("ip", ["127.0.0.1", "169.254.169.254", "192.168.1.1", "::1"])
def test_ensure_public_smtp_host_blocks_internal(monkeypatch, ip):
    _resolve_to(monkeypatch, ip)
    with pytest.raises(ValueError):
        ensure_public_smtp_host("x.example", 587)


def test_ensure_public_smtp_host_blocks_port(monkeypatch):
    _resolve_to(monkeypatch, "93.184.216.34")
    with pytest.raises(ValueError):
        ensure_public_smtp_host("x.example", 6379)
    ensure_public_smtp_host("x.example", 465)


# --- WeasyPrint ---


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://169.254.169.254/", "https://x.lt"])
def test_pdf_fetcher_blocks_non_data(url):
    with pytest.raises(ValueError):
        _data_only_fetcher().fetch(url)


def test_pdf_fetcher_allows_data_uri():
    _data_only_fetcher().fetch("data:text/plain;base64,dGVzdA==")


# --- Excel formulės ---


def test_excel_formula_neutralized(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(['=HYPERLINK("http://evil")', "+1", "normalus"])
    _neutralize_formulas(ws)
    path = tmp_path / "x.xlsx"
    wb.save(path)
    cell = load_workbook(path).active["A1"]
    assert cell.data_type == "s"
    assert cell.value == '=HYPERLINK("http://evil")'
    assert cell.quotePrefix
    assert load_workbook(path).active["B1"].quotePrefix
    assert not load_workbook(path).active["C1"].quotePrefix


# --- šifravimo raktas ---


def test_encrypted_field_rotates_from_legacy_key(tenant, settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    fields._fernet.cache_clear()
    smtp = SmtpSettings.objects.create(tenant=tenant, host="smtp.x.lt", password="senas")

    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    fields._fernet.cache_clear()
    smtp.refresh_from_db()
    assert smtp.password == "senas"
    smtp.save(update_fields=["password"])

    settings.SECRET_KEY = "kitas-secret-key"
    fields._fernet.cache_clear()
    smtp.refresh_from_db()
    assert smtp.password == "senas"
    fields._fernet.cache_clear()


# --- Cloudflare Access ---


@pytest.fixture
def cf_access(settings, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.CF_ACCESS_TEAM_DOMAIN = "team.cloudflareaccess.com"
    settings.CF_ACCESS_AUD = "aud123"

    class FakeJwks:
        def get_signing_key_from_jwt(self, token):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.setattr("apps.core.middleware._jwks_client", lambda team: FakeJwks())

    def make(aud="aud123", iss="https://team.cloudflareaccess.com", signer=key):
        now = datetime.now(UTC)
        return jwt.encode(
            {"aud": aud, "iss": iss, "iat": now, "exp": now + timedelta(minutes=5)},
            signer,
            algorithm="RS256",
        )

    return make


def test_admin_blocked_without_access_jwt(client, cf_access):
    assert client.get("/admin/login/").status_code == 403


def test_admin_allowed_with_valid_access_jwt(client, cf_access):
    resp = client.get("/admin/login/", HTTP_CF_ACCESS_JWT_ASSERTION=cf_access())
    assert resp.status_code == 200


def test_admin_rejects_wrong_aud_or_key(client, cf_access):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for token in (cf_access(aud="kitas"), cf_access(signer=other), "garbage"):
        resp = client.get("/admin/login/", HTTP_CF_ACCESS_JWT_ASSERTION=token)
        assert resp.status_code == 403


def test_api_not_affected_by_access(client, cf_access):
    assert client.get("/api/v1/health").status_code == 200


def test_admin_open_when_access_not_configured(client):
    assert client.get("/admin/login/").status_code == 200


def test_reencrypt_migration_reverse_restores_legacy(tenant, settings):
    import importlib

    from django.apps import apps
    from django.db import connection

    mig = importlib.import_module("apps.mailer.migrations.0002_reencrypt_smtp_passwords")
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    fields._fernet.cache_clear()
    smtp = SmtpSettings.objects.create(tenant=tenant, host="smtp.x.lt", password="slaptas")

    mig.back_to_legacy(apps, type("Editor", (), {"connection": connection})())

    settings.FIELD_ENCRYPTION_KEY = ""
    fields._fernet.cache_clear()
    smtp.refresh_from_db()
    assert smtp.password == "slaptas"
    fields._fernet.cache_clear()


def test_reencrypt_migration_reverse_fails_on_unreadable_password(tenant, settings):
    import importlib

    from django.apps import apps
    from django.db import connection

    mig = importlib.import_module("apps.mailer.migrations.0002_reencrypt_smtp_passwords")
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    fields._fernet.cache_clear()
    SmtpSettings.objects.create(tenant=tenant, host="smtp.x.lt", password="slaptas")
    settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    fields._fernet.cache_clear()

    with pytest.raises(RuntimeError, match="neiššifruojamas"):
        mig.back_to_legacy(apps, type("Editor", (), {"connection": connection})())
    fields._fernet.cache_clear()
