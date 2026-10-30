from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.tenancy.models import SellerProfile, Tenant, TenantMembership, User

admin.site.register(User, UserAdmin)


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
