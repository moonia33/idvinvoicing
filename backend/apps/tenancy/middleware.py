from apps.tenancy.models import Tenant, TenantMembership


class TenantMiddleware:
    """Priskiria request.tenant (session['tenant_id'] arba pirmą) ir request.tenant_role."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.tenant_role = None
        if request.user.is_authenticated:
            tenants = Tenant.objects.filter(memberships__user=request.user)
            request.tenant = (
                tenants.filter(id=request.session.get("tenant_id")).first() or tenants.first()
            )
            if request.tenant:
                request.tenant_role = (
                    TenantMembership.objects.filter(user=request.user, tenant=request.tenant)
                    .values_list("role", flat=True)
                    .first()
                )
        return self.get_response(request)
