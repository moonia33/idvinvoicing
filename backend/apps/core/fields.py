import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


@lru_cache
def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedCharField(models.CharField):
    """CharField, DB saugomas užšifruotas (Fernet iš DJANGO_SECRET_KEY)."""

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
