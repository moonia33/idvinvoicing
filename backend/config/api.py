from django.conf import settings
from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja.security import SessionAuth

from apps.invoicing.api import router as invoicing_router
from apps.ledger.api import router as ledger_router
from apps.mailer.api import router as mailer_router
from apps.purchases.api import router as purchases_router
from apps.reports.api import router as reports_router
from apps.taxes.api import router as taxes_router
from apps.tenancy.api import router as tenancy_router

READ_ONLY_ROLES = {"accountant"}
READ_ONLY_ALLOWED = ("/api/v1/tenants/switch",)


class TenantSessionAuth(SessionAuth):
    """Sesijos auth + rolė „Buhalteris“ aktyvioje veikloje gali tik skaityti."""

    def authenticate(self, request, key):
        user = super().authenticate(request, key)
        if (
            user
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and getattr(request, "tenant_role", None) in READ_ONLY_ROLES
            and not request.path.startswith(READ_ONLY_ALLOWED)
        ):
            raise HttpError(403, "Buhalterio rolė gali tik peržiūrėti")
        return user


api = NinjaAPI(
    title="IDV Apskaita API",
    urls_namespace="api",
    auth=TenantSessionAuth(),
    docs_url="/docs" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

api.add_router("", tenancy_router)
api.add_router("", invoicing_router)
api.add_router("", purchases_router)
api.add_router("", ledger_router)
api.add_router("", mailer_router)
api.add_router("", taxes_router)
api.add_router("", reports_router)


@api.get("/health", auth=None, tags=["meta"])
def health(request):
    return {"status": "ok"}
