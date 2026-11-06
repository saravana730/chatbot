from typing import Annotated, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession, require_csrf
from app.schemas.auth import LoginRequest, MessageOut, UserOut
from app.services.auth_service import AuthError, authenticate_user, issue_tokens, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _set_auth_cookies(response: Response, tokens: dict[str, str]) -> None:
    common = {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        "access_token",
        tokens["access_token"],
        max_age=settings.access_token_expire_minutes * 60,
        **common,
    )
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        **common,
    )
    # CSRF token is readable by JS for double-submit
    response.set_cookie(
        "csrf_token",
        tokens["csrf_token"],
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, path="/")


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    response: Response,
    db: DBSession,
) -> UserOut:
    try:
        user = await authenticate_user(db, body.email, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc
    tokens = issue_tokens(user)
    _set_auth_cookies(response, tokens)
    return UserOut.model_validate(user)


@router.post("/logout", response_model=MessageOut, dependencies=[Depends(require_csrf)])
async def logout(response: Response) -> MessageOut:
    _clear_auth_cookies(response)
    return MessageOut(detail="Logged out")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/refresh", response_model=UserOut)
async def refresh(
    response: Response,
    db: DBSession,
    refresh_token: Annotated[Optional[str], Cookie(alias="refresh_token")] = None,
) -> UserOut:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        user, tokens = await rotate_refresh_token(db, refresh_token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.message) from exc
    _set_auth_cookies(response, tokens)
    return UserOut.model_validate(user)
