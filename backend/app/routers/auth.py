"""Local single-user authentication."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..security import create_access_token, get_current_user, verify_credentials

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    if not verify_credentials(form.username, form.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(form.username)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(user: str = Depends(get_current_user)):
    return {"username": user}
