import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

_FERNET: Optional[Fernet] = None

KEY_ENV = "EMAIL_ENCRYPTION_KEY"


def get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.environ.get(KEY_ENV)
    if not key:
        # Generate ephemeral key (recommend user sets EMAIL_ENCRYPTION_KEY to persist)
        key = Fernet.generate_key().decode()
        os.environ[KEY_ENV] = key
    _FERNET = Fernet(key.encode())
    return _FERNET


def encrypt_secret(plain: str) -> str:
    f = get_fernet()
    return f.encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    f = get_fernet()
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt stored secret; key mismatch or corrupted data")
