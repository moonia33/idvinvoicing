import pytest
from django.core import mail
from django.test import Client

from apps.tenancy.models import LoginCode, TenantMembership, User
from tests.conftest import post_json

pytestmark = pytest.mark.django_db


def _code_from_mail() -> str:
    return mail.outbox[-1].subject.rsplit(" ", 1)[-1]


def test_code_email_shows_code_in_subject_and_html(client, emailed_user):
    post_json(client, "/api/v1/auth/otp/request", {"email": emailed_user.email})
    msg = mail.outbox[-1]
    code = _code_from_mail()
    assert msg.subject == f"Prisijungimo kodas: {code}"
    assert msg.body.startswith(f"Jūsų prisijungimo kodas: {code}")
    html, mime = msg.alternatives[0]
    assert mime == "text/html" and f">{code}</p>" in html


@pytest.fixture
def emailed_user(user):
    user.email = "tomas@example.lt"
    user.save(update_fields=["email"])
    return user


def test_otp_login_flow(client, emailed_user, tenant):
    resp = post_json(client, "/api/v1/auth/otp/request", {"email": "Tomas@Example.lt"})
    assert resp.status_code == 200
    assert mail.outbox[-1].to == ["tomas@example.lt"]
    code = _code_from_mail()
    assert LoginCode.objects.get().code_hash != code

    resp = post_json(client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": code})
    assert resp.status_code == 200
    assert resp.json()["current_tenant_id"] == tenant.id
    assert client.get("/api/v1/auth/me").status_code == 200

    # kodas vienkartinis
    client.post("/api/v1/auth/logout")
    resp = post_json(client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": code})
    assert resp.status_code == 401


def test_otp_unknown_email_same_response(client):
    resp = post_json(client, "/api/v1/auth/otp/request", {"email": "nera@example.lt"})
    assert resp.status_code == 200
    assert "Jei toks" in resp.json()["detail"]
    assert mail.outbox == []


def test_otp_wrong_code_attempts_burn_code(client, emailed_user):
    post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    code = _code_from_mail()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        resp = post_json(
            client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": wrong}
        )
        assert resp.status_code == 401
    resp = post_json(client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": code})
    assert resp.status_code == 401


def test_otp_request_rate_limited(client, emailed_user):
    for _ in range(5):
        post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    assert len(mail.outbox) == 3


def test_new_code_invalidates_old(client, emailed_user):
    post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    old = _code_from_mail()
    post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    new = _code_from_mail()
    if old != new:
        resp = post_json(
            client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": old}
        )
        assert resp.status_code == 401
    resp = post_json(client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": new})
    assert resp.status_code == 200


def test_password_endpoints_removed(client, user):
    resp = post_json(client, "/api/v1/auth/login", {"username": "tomas", "password": "slaptas123"})
    assert resp.status_code in (404, 405)


def test_invite_new_user_and_manage_other_tenant(api_client, tenant):
    client = Client()
    resp = post_json(
        api_client, "/api/v1/tenants/members", {"email": "Ona@Example.lt", "role": "member"}
    )
    assert resp.status_code == 200
    ona = User.objects.get(email="ona@example.lt")
    assert not ona.has_usable_password()
    assert mail.outbox[-1].to == ["ona@example.lt"]
    assert "Kvietimas" in mail.outbox[-1].subject

    members = api_client.get("/api/v1/tenants/members").json()
    assert {m["email"] for m in members} == {"", "ona@example.lt"}

    # Ona prisijungia kodu ir mato kviečiančiojo veiklą
    post_json(client, "/api/v1/auth/otp/request", {"email": "ona@example.lt"})
    resp = post_json(
        client, "/api/v1/auth/otp/verify", {"email": "ona@example.lt", "code": _code_from_mail()}
    )
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()["tenants"]] == [tenant.id]

    resp = post_json(api_client, "/api/v1/tenants/members", {"email": "ona@example.lt"})
    assert resp.status_code == 400


def test_invite_existing_user_with_own_tenant(api_client, other_user, other_tenant, tenant):
    other_user.email = "ona@example.lt"
    other_user.save(update_fields=["email"])
    resp = post_json(
        api_client, "/api/v1/tenants/members", {"email": "ona@example.lt", "role": "owner"}
    )
    assert resp.status_code == 200
    assert set(
        TenantMembership.objects.filter(user=other_user).values_list("tenant_id", flat=True)
    ) == {tenant.id, other_tenant.id}


def test_only_owner_manages_members_and_settings(client, user, tenant, other_user):
    m = TenantMembership.objects.create(user=other_user, tenant=tenant, role="member")
    client.force_login(other_user)
    client.cookies.load({"csrftoken": "t"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "t"
    assert client.get("/api/v1/tenants/members").status_code == 200
    assert post_json(client, "/api/v1/tenants/members", {"email": "x@x.lt"}).status_code == 403
    assert client.delete(f"/api/v1/tenants/members/{m.id}").status_code == 403
    resp = client.put("/api/v1/profile", {"seller_name": "X"}, content_type="application/json")
    assert resp.status_code == 403


def test_accountant_is_read_only(client, user, tenant, other_user):
    TenantMembership.objects.create(user=other_user, tenant=tenant, role="accountant")
    client.force_login(other_user)
    client.cookies.load({"csrftoken": "t"})
    client.defaults["HTTP_X_CSRFTOKEN"] = "t"
    assert client.get("/api/v1/profile").status_code == 200
    resp = post_json(client, "/api/v1/clients", {"name": "Klientas"})
    assert resp.status_code == 403
    assert post_json(client, "/api/v1/tenants/switch", {"tenant_id": tenant.id}).status_code == 200


def test_last_owner_cannot_be_removed_or_demoted(api_client, tenant):
    owner = TenantMembership.objects.get(tenant=tenant)
    assert api_client.delete(f"/api/v1/tenants/members/{owner.id}").status_code == 400
    resp = api_client.patch(
        f"/api/v1/tenants/members/{owner.id}", {"role": "member"}, content_type="application/json"
    )
    assert resp.status_code == 400
    resp = api_client.patch(
        f"/api/v1/tenants/members/{owner.id}", {"role": "boss"}, content_type="application/json"
    )
    assert resp.status_code == 400


def test_members_isolated_between_tenants(api_client, other_tenant, other_user):
    m = TenantMembership.objects.get(tenant=other_tenant)
    assert api_client.delete(f"/api/v1/tenants/members/{m.id}").status_code == 404
    emails = [x["email"] for x in api_client.get("/api/v1/tenants/members").json()]
    assert other_user.email not in emails or other_user.email == ""


def test_code_bound_to_email_at_issue(client, emailed_user):
    post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    code = _code_from_mail()
    emailed_user.email = "naujas@example.lt"
    emailed_user.save(update_fields=["email"])
    resp = post_json(
        client, "/api/v1/auth/otp/verify", {"email": "naujas@example.lt", "code": code}
    )
    assert resp.status_code == 401


def test_otp_session_does_not_open_admin(client, emailed_user):
    emailed_user.is_staff = emailed_user.is_superuser = True
    emailed_user.save()
    post_json(client, "/api/v1/auth/otp/request", {"email": "tomas@example.lt"})
    post_json(
        client, "/api/v1/auth/otp/verify", {"email": "tomas@example.lt", "code": _code_from_mail()}
    )
    assert client.get("/admin/").status_code == 302
