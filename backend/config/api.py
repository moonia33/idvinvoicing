from ninja import NinjaAPI
from ninja.security import django_auth

from apps.invoicing.api import router as invoicing_router
from apps.tenancy.api import router as tenancy_router

api = NinjaAPI(
    title="IDV Apskaita API",
    urls_namespace="api",
    auth=django_auth,
)

api.add_router("", tenancy_router)
api.add_router("", invoicing_router)


@api.get("/health", auth=None, tags=["meta"])
def health(request):
    return {"status": "ok"}
