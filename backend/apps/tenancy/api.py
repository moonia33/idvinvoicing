from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from ninja import Router, Status
from ninja.errors import HttpError

from apps.tenancy.models import SellerProfile, Tenant, TenantMembership
from apps.tenancy.schemas import (
    LoginIn,
    MeOut,
    ProfileIn,
    ProfileOut,
    TenantIn,
    TenantOut,
    TenantSwitchIn,
)

router = Router()


def current_tenant(request) -> Tenant:
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise HttpError(403, "Vartotojas neturi veiklos (tenant)")
    return tenant


@router.get("/auth/csrf", auth=None)
def csrf(request):
    return {"csrfToken": get_token(request)}


@router.post("/auth/login", auth=None, response={200: MeOut, 401: dict})
def login_view(request, data: LoginIn):
    user = authenticate(request, username=data.username, password=data.password)
    if user is None:
        return Status(401, {"detail": "Neteisingas prisijungimo vardas arba slaptažodis"})
    login(request, user)
    tenant = Tenant.objects.filter(memberships__user=user).first()
    if tenant:
        request.session["tenant_id"] = tenant.id
        request.tenant = tenant
    return Status(200, me(request))


@router.post("/auth/logout", auth=None)
def logout_view(request):
    logout(request)
    return {"detail": "ok"}


@router.get("/auth/me", response=MeOut)
def me(request):
    memberships = (
        TenantMembership.objects.filter(user=request.user)
        .select_related("tenant")
        .order_by("tenant__name")
    )
    tenant = getattr(request, "tenant", None)
    return {
        "id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "tenants": [
            {"id": m.tenant.id, "name": m.tenant.name, "role": m.role} for m in memberships
        ],
        "current_tenant_id": tenant.id if tenant else None,
    }


@router.get("/tenants", response=list[TenantOut])
def list_tenants(request):
    memberships = TenantMembership.objects.filter(user=request.user).select_related("tenant")
    return [{"id": m.tenant.id, "name": m.tenant.name, "role": m.role} for m in memberships]


@router.post("/tenants", response=TenantOut)
def create_tenant(request, data: TenantIn):
    tenant = Tenant.objects.create(name=data.name)
    TenantMembership.objects.create(
        user=request.user, tenant=tenant, role=TenantMembership.Role.OWNER
    )
    request.session["tenant_id"] = tenant.id
    return {"id": tenant.id, "name": tenant.name, "role": TenantMembership.Role.OWNER}


@router.post("/tenants/switch")
def switch_tenant(request, data: TenantSwitchIn):
    if not TenantMembership.objects.filter(user=request.user, tenant_id=data.tenant_id).exists():
        raise HttpError(403, "Nėra prieigos prie šios veiklos")
    request.session["tenant_id"] = data.tenant_id
    return {"detail": "ok"}


@router.get("/profile", response={200: ProfileOut, 404: dict})
def get_profile(request):
    tenant = current_tenant(request)
    try:
        p = tenant.profile
    except SellerProfile.DoesNotExist:
        return Status(404, {"detail": "Profilis nesukurtas"})
    return Status(200, p)


@router.put("/profile", response=ProfileOut)
def upsert_profile(request, data: ProfileIn):
    tenant = current_tenant(request)
    profile, _ = SellerProfile.objects.update_or_create(tenant=tenant, defaults=data.model_dump())
    return profile
