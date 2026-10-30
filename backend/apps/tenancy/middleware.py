from apps.tenancy.models import Tenant


class TenantMiddleware:
    """Priskiria request.tenant pagal session['tenant_id'] arba pirmą vartotojo tenant'ą."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        if request.user.is_authenticated:
            tenants = Tenant.objects.filter(memberships__user=request.user)
            request.tenant = (
                tenants.filter(id=request.session.get("tenant_id")).first() or tenants.first()
            )
        return self.get_response(request)
