from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.tenancy.models import SellerProfile, Tenant, TenantMembership, User
from apps.tenancy.otp import OTP_SESSION_FLAG

admin.site.register(User, UserAdmin)

_admin_has_permission = admin.site.has_permission


def _has_admin_permission(request):
    """/admin/ reikalauja prisijungimo slaptažodžiu; OTP sesija jo neatveria."""
    return _admin_has_permission(request) and not request.session.get(OTP_SESSION_FLAG)


admin.site.has_permission = _has_admin_permission  # type: ignore[method-assign]


@receiver(user_logged_in)
def _clear_otp_flag(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session.pop(OTP_SESSION_FLAG, None)


class MembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    inlines = [MembershipInline]


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ["seller_name", "tenant", "accounting_basis", "deductions_method"]
