"""Password hashing and JWT issuing/verification."""
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt silently truncates at 72 bytes; refuse rather than hash a prefix.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False
    try:
        return pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> str | None:
    """Return the subject (user id as string), or None if the token is bad.

    PyJWT rather than python-jose: jose has been unmaintained since 2021 and
    carries CVE-2024-33663 (algorithm confusion) and CVE-2024-33664 (a
    decompression bomb reachable through JWE). The algorithms list below
    already pinned the first one shut, but an unmaintained library sitting on
    the authentication path is not worth defending. PyJWT is a drop-in for the
    two calls this module makes.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
