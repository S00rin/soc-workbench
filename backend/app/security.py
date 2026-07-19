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
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models.governance import UserAccount

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


def verify_credentials(username: str, password: str, db: Session | None = None) -> bool:
    """Compatibility wrapper; database authentication is authoritative."""
    if db is not None:
        from .services.access_control import authenticate
        return authenticate(db, username, password) is not None
    return username == settings.admin_username and password == settings.admin_password


@dataclass(frozen=True)
class AuthContext:
    username: str
    tenant_id: str
    role: str
    user_id: int = 0
    display_name: str = ""
    module_permissions: tuple[str, ...] = ()
    must_change_password: bool = False


def create_access_token(subject: str | UserAccount, *, tenant_id: str = "", role: str = "", user_id: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    if isinstance(subject, UserAccount):
        user = subject
        subject = user.username
        tenant_id = user.tenant_id
        role = user.role
        user_id = user.id
    payload = {
        "sub": subject,
        "uid": user_id,
        "tenant": tenant_id or settings.default_tenant_id,
        "role": role or settings.admin_role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
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
        return payload
    except JWTError:
        raise credentials_exception


def resolve_token_context(token: str, db: Session) -> AuthContext:
    payload = _decode_token(token)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User is inactive or no longer exists",
        headers={"WWW-Authenticate": "Bearer"},
    )
    tenant_id = payload.get("tenant") or settings.default_tenant_id
    query = db.query(UserAccount).filter(UserAccount.tenant_id == tenant_id, UserAccount.active.is_(True))
    if payload.get("uid"):
        query = query.filter(UserAccount.id == int(payload["uid"]))
    else:
        query = query.filter(UserAccount.username == payload["sub"])
    user = query.first()
    if user is None:
        raise credentials_exception
    return AuthContext(
        username=user.username,
        tenant_id=user.tenant_id,
        role=user.role,
        user_id=user.id,
        display_name=user.display_name or user.username,
        module_permissions=tuple(user.module_permissions or []),
        must_change_password=user.must_change_password,
    )


def get_auth_context(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> AuthContext:
    return resolve_token_context(token, db)


def get_current_user(context: AuthContext = Depends(get_auth_context)) -> str:
    return context.username


def require_admin(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if context.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return context
