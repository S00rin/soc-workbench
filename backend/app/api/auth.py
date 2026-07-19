"""Single-user local login (Phase 1)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.governance import UserAccount
from ..schemas import Token, UserOut
from ..security import AuthContext, create_access_token, get_auth_context
from ..services.access_control import authenticate

router = APIRouter(prefix="/api/auth", tags=["auth"])
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempt_lock = threading.Lock()
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_FAILURES = 6


def _attempt_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().casefold()}"


def _check_login_rate(key: str) -> None:
    now = time.monotonic()
    with _attempt_lock:
        values = _attempts[key]
        while values and values[0] <= now - _LOGIN_WINDOW_SECONDS:
            values.popleft()
        if len(values) >= _LOGIN_MAX_FAILURES:
            retry_after = max(1, int(_LOGIN_WINDOW_SECONDS - (now - values[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed sign-in attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )


@router.post("/login", response_model=Token)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    key = _attempt_key(request, form.username)
    _check_login_rate(key)
    user = authenticate(db, form.username, form.password)
    if user is None:
        with _attempt_lock:
            _attempts[key].append(time.monotonic())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    with _attempt_lock:
        _attempts.pop(key, None)
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=UserOut)
def me(context: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> UserOut:
    user = db.query(UserAccount).filter(UserAccount.id == context.user_id).first()
    return UserOut(
        username=context.username,
        tenant_id=context.tenant_id,
        role=context.role,
        display_name=context.display_name,
        module_permissions=list(context.module_permissions),
        must_change_password=bool(user and user.must_change_password),
    )
