import pytest
from django.test import Client

from apps.tenancy.models import SellerProfile, Tenant, TenantMembership, User

CSRF_TOKEN = "testcsrf"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tomas", password="slaptas123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="ona", password="slaptas123")


@pytest.fixture
def tenant(db, user):
    t = Tenant.objects.create(name="IT konsultacijos")
    TenantMembership.objects.create(user=user, tenant=t, role=TenantMembership.Role.OWNER)
    SellerProfile.objects.create(
        tenant=t, seller_name="Tomas IV", invoice_series="SF", iban="LT001"
    )
    return t


@pytest.fixture
def other_tenant(db, other_user):
    t = Tenant.objects.create(name="Kita veikla")
    TenantMembership.objects.create(user=other_user, tenant=t, role=TenantMembership.Role.OWNER)
    return t


@pytest.fixture
def api_client(client, user, tenant):
    """Django test client: prisijungęs vartotojas + CSRF pora."""
    client.force_login(user)
    client.cookies.load({"csrftoken": CSRF_TOKEN})
    client.defaults["HTTP_X_CSRFTOKEN"] = CSRF_TOKEN
    return client


def post_json(c: Client, url: str, data: dict):
    return c.post(url, data, content_type="application/json")
