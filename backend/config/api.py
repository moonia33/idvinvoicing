from ninja import NinjaAPI

api = NinjaAPI(
    title="IDV Apskaita API",
    urls_namespace="api",
)


@api.get("/health", tags=["meta"])
def health(request):
    return {"status": "ok"}
