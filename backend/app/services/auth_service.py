from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


class AuthError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")
    return user


def issue_tokens(user: User) -> dict[str, str]:
    return {
        "access_token": create_access_token(str(user.id), user.email),
        "refresh_token": create_refresh_token(str(user.id)),
        "csrf_token": create_csrf_token(),
    }


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> tuple[User, dict[str, str]]:
    try:
        payload = decode_token(refresh_token)
    except Exception as exc:
        raise AuthError("Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        raise AuthError("Invalid refresh token type")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError("User not found")
    return user, issue_tokens(user)


async def ensure_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(email=email.lower(), password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    return user
