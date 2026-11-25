from functools import lru_cache

import jwt
from django.conf import settings
from django.http import HttpResponseForbidden


@lru_cache
def _jwks_client(team_domain: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", cache_keys=True)


def verify_access_token(token: str) -> dict:
    team = settings.CF_ACCESS_TEAM_DOMAIN
    key = _jwks_client(team).get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key=key,
        algorithms=["RS256"],
        audience=settings.CF_ACCESS_AUD,
        issuer=f"https://{team}",
    )


class CloudflareAccessMiddleware:
    """Apsaugoti keliai (/admin/) leidžiami tik su galiojančiu Cloudflare Access JWT.

    Taip Access neapeinamas, kreipiantis į serverį tiesiai per IP.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.CF_ACCESS_AUD
            and settings.CF_ACCESS_TEAM_DOMAIN
            and request.path.startswith(settings.CF_ACCESS_PROTECTED_PREFIXES)
        ):
            token = request.headers.get("Cf-Access-Jwt-Assertion", "")
            try:
                verify_access_token(token)
            except Exception:
                return HttpResponseForbidden("Cloudflare Access required")
        return self.get_response(request)
