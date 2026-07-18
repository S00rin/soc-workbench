"""Single-user local authentication and secret encryption.

- Login: username/password from env -> JWT bearer token.
- Secret encryption: Fernet key derived from SECRET_KEY, used to encrypt
  connector credentials and the tokenization mapping at rest in SQLite.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import get_settings

settings = get_settings()
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    if plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if ciphertext == "":
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def mask_secret(value: str, visible: int = 4) -> str:
    """Never show a full secret. Returns e.g. '****abcd'."""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


def verify_credentials(username: str, password: str) -> bool:
    return (
        username == settings.admin_username
        and password == settings.admin_password
    )


@dataclass(frozen=True)
class AuthContext:
    username: str
    tenant_id: str
    role: str


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "tenant": settings.default_tenant_id,
        "role": settings.admin_role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception
        return subject
    except JWTError:
        raise credentials_exception


def get_auth_context(token: str = Depends(oauth2_scheme)) -> AuthContext:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise credentials_exception
        return AuthContext(
            username=subject,
            tenant_id=payload.get("tenant") or settings.default_tenant_id,
            role=payload.get("role") or settings.admin_role,
        )
    except JWTError:
        raise credentials_exception


def require_admin(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if context.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return context
