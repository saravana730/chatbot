"""Create the default bootstrap user if missing."""

import asyncio
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.postgres import AsyncSessionLocal
from app.models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def bootstrap() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == settings.bootstrap_email.lower())
        )
        user = result.scalar_one_or_none()
        if user:
            logger.info("Bootstrap user already exists: %s", settings.bootstrap_email)
            return
        user = User(
            email=settings.bootstrap_email.lower(),
            password_hash=hash_password(settings.bootstrap_password),
        )
        session.add(user)
        await session.commit()
        logger.info("Created bootstrap user: %s", settings.bootstrap_email)


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
