"""Single-user local login (Phase 1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..schemas import Token, UserOut
from ..security import AuthContext, create_access_token, get_auth_context, verify_credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()) -> Token:
    if not verify_credentials(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    return Token(access_token=create_access_token(form.username))


@router.get("/me", response_model=UserOut)
def me(context: AuthContext = Depends(get_auth_context)) -> UserOut:
    return UserOut(username=context.username, tenant_id=context.tenant_id, role=context.role)
