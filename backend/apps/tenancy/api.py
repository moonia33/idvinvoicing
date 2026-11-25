import base64
from io import BytesIO

from django.contrib.auth import login, logout
from django.db import transaction
from django.middleware.csrf import get_token
from ninja import File, Router, Status
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.tenancy import otp
from apps.tenancy.models import SellerProfile, Tenant, TenantMembership, User
from apps.tenancy.schemas import (
    MemberIn,
    MemberOut,
    MemberRoleIn,
    MeOut,
    OtpRequestIn,
    OtpVerifyIn,
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


def require_owner(request) -> Tenant:
    tenant = current_tenant(request)
    if request.tenant_role != TenantMembership.Role.OWNER:
        raise HttpError(403, "Tik veiklos savininkas gali tai keisti")
    return tenant


@router.get("/auth/csrf", auth=None)
def csrf(request):
    return {"csrfToken": get_token(request)}


OTP_SENT = {"detail": "Jei toks el. paštas registruotas, išsiuntėme prisijungimo kodą"}


@router.post("/auth/otp/request", auth=None)
def otp_request(request, data: OtpRequestIn):
    user = otp.find_user(data.email)
    if user is not None:
        code = otp.issue_code(user)
        if code:
            otp.send_code(user, code, request)
    return OTP_SENT


@router.post("/auth/otp/verify", auth=None, response={200: MeOut, 401: dict})
def otp_verify(request, data: OtpVerifyIn):
    user = otp.find_user(data.email)
    if user is None or not otp.verify_code(user, data.code):
        return Status(401, {"detail": "Neteisingas arba nebegaliojantis kodas"})
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session[otp.OTP_SESSION_FLAG] = True
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


ROLES = {r.value for r in TenantMembership.Role}


def _member_out(m: TenantMembership) -> dict:
    u = m.user
    return {
        "id": m.id,
        "user_id": u.id,
        "email": u.email,
        "name": u.get_full_name() or u.username,
        "role": m.role,
    }


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise HttpError(400, "Neteisinga rolė")


def _ensure_other_owner(m: TenantMembership) -> None:
    if (
        m.role == TenantMembership.Role.OWNER
        and not TenantMembership.objects.filter(tenant=m.tenant, role=TenantMembership.Role.OWNER)
        .exclude(id=m.id)
        .exists()
    ):
        raise HttpError(400, "Veikla turi turėti bent vieną savininką")


@router.get("/tenants/members", response=list[MemberOut])
def list_members(request):
    tenant = current_tenant(request)
    qs = TenantMembership.objects.filter(tenant=tenant).select_related("user").order_by("id")
    return [_member_out(m) for m in qs]


@router.post("/tenants/members", response={200: MemberOut, 400: dict})
def invite_member(request, data: MemberIn):
    tenant = require_owner(request)
    _check_role(data.role)
    email = data.email.strip().lower()
    if "@" not in email or len(email) > 150:
        return Status(400, {"detail": "Neteisingas el. pašto adresas"})
    with transaction.atomic():
        user = otp.find_user(email)
        if user is None:
            if User.objects.filter(username=email).exists():
                return Status(400, {"detail": "Toks vartotojas jau yra, bet neaktyvus"})
            user = User(username=email, email=email)
            user.set_unusable_password()
            user.save()
        if TenantMembership.objects.filter(user=user, tenant=tenant).exists():
            return Status(400, {"detail": "Šis vartotojas jau yra veiklos narys"})
        m = TenantMembership.objects.create(user=user, tenant=tenant, role=data.role)
    otp.send_invite(user, tenant.name, request.user, request)
    return Status(200, _member_out(m))


@router.patch("/tenants/members/{member_id}", response=MemberOut)
def change_member_role(request, member_id: int, data: MemberRoleIn):
    tenant = require_owner(request)
    _check_role(data.role)
    m = TenantMembership.objects.select_related("user", "tenant").filter(
        tenant=tenant, id=member_id
    )
    member = m.first()
    if member is None:
        raise HttpError(404, "Narys nerastas")
    if data.role != TenantMembership.Role.OWNER:
        _ensure_other_owner(member)
    member.role = data.role
    member.save(update_fields=["role"])
    return _member_out(member)


@router.delete("/tenants/members/{member_id}")
def remove_member(request, member_id: int):
    tenant = require_owner(request)
    member = TenantMembership.objects.select_related("tenant").filter(tenant=tenant, id=member_id)
    m = member.first()
    if m is None:
        raise HttpError(404, "Narys nerastas")
    _ensure_other_owner(m)
    m.delete()
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
    tenant = require_owner(request)
    profile, _ = SellerProfile.objects.update_or_create(tenant=tenant, defaults=data.model_dump())
    return profile


MAX_LOGO_BYTES = 3 * 1024 * 1024  # 3 MB – iki sumažinimo


@router.post("/profile/logo", response=ProfileOut)
def upload_logo(request, file: UploadedFile = File(...)):  # noqa: B008
    tenant = require_owner(request)
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
    tenant = require_owner(request)
    try:
        profile = tenant.profile
    except SellerProfile.DoesNotExist:
        raise HttpError(404, "Profilis nesukurtas") from None
    profile.logo = ""
    profile.save(update_fields=["logo"])
    return profile
