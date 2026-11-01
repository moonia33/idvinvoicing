import base64
from io import BytesIO

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.middleware.csrf import get_token
from ninja import File, Router, Schema, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

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


class PasswordIn(Schema):
    old_password: str
    new_password: str


@router.post("/auth/password", response={200: dict, 400: dict})
def change_password(request, data: PasswordIn):
    user = request.user
    if not user.check_password(data.old_password):
        return Status(400, {"detail": "Neteisingas dabartinis slaptažodis"})
    if len(data.new_password) < 8:
        return Status(400, {"detail": "Naujas slaptažodis per trumpas (min. 8 simboliai)"})
    user.set_password(data.new_password)
    user.save(update_fields=["password"])
    update_session_auth_hash(request, user)
    return Status(200, {"detail": "Slaptažodis pakeistas"})


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


MAX_LOGO_BYTES = 3 * 1024 * 1024  # 3 MB – iki sumažinimo


@router.post("/profile/logo", response=ProfileOut)
def upload_logo(request, file: UploadedFile = File(...)):  # noqa: B008
    tenant = current_tenant(request)
    data = file.read()
    if len(data) > MAX_LOGO_BYTES:
        raise HttpError(400, "Failas per didelis (maks. 3 MB)")
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as raw:
            img = raw.convert("RGBA") if raw.mode in ("P", "LA") else raw.copy()
        img.thumbnail((480, 480))
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
    except Exception:
        raise HttpError(400, "Neteisingas paveikslėlio formatas (leidžiama PNG/JPG/WebP)") from None
    profile, _ = SellerProfile.objects.get_or_create(
        tenant=tenant, defaults={"seller_name": tenant.name}
    )
    profile.logo = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    profile.save(update_fields=["logo"])
    return profile


@router.delete("/profile/logo", response=ProfileOut)
def delete_logo(request):
    tenant = current_tenant(request)
    try:
        profile = tenant.profile
    except SellerProfile.DoesNotExist:
        raise HttpError(404, "Profilis nesukurtas") from None
    profile.logo = ""
    profile.save(update_fields=["logo"])
    return profile
