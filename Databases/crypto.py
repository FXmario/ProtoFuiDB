import base64
import hashlib

from django.conf import settings
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Derive a stable Fernet key from Django's SECRET_KEY."""
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
