from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Vienas vartotojas gali priklausyti keliems tenant'ams (veikloms)."""

    pass
