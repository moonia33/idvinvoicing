import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models


def _legacy_key() -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())


@lru_cache
def _fernet() -> MultiFernet:
    """Pirmas raktas šifruoja; senas (iš SECRET_KEY) lieka tik iššifravimui."""
    keys = [Fernet(_legacy_key())]
    if settings.FIELD_ENCRYPTION_KEY:
        keys.insert(0, Fernet(settings.FIELD_ENCRYPTION_KEY.encode()))
    return MultiFernet(keys)


class EncryptedCharField(models.CharField):
    """CharField, DB saugomas užšifruotas (Fernet, DJANGO_FIELD_ENCRYPTION_KEY)."""

    def get_prep_value(self, value):
        if value:
            value = _fernet().encrypt(value.encode()).decode()
        return super().get_prep_value(value)

    def from_db_value(self, value, expression, connection):
        if value:
            try:
                value = _fernet().decrypt(value.encode()).decode()
            except Exception:
                value = ""
        return value
