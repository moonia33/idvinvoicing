"""Nustatymai testams ir mypy: lokaliai DEBUG režimas be produkcinių raktų."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")

from config.settings import *  # noqa: E402, F403

# Testai nekviečia collectstatic, todėl manifest saugykla nenaudojama.
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

OTP_EMAIL_ASYNC = False
