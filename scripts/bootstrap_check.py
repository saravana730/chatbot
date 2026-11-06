import asyncio
import subprocess
import sys

subprocess.check_call(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "sqlalchemy==2.0.36",
        "asyncpg",
        "argon2-cffi",
        "PyJWT",
        "pydantic",
        "pydantic-settings",
        "email-validator",
        "greenlet",
    ]
)

from app.bootstrap import bootstrap

asyncio.run(bootstrap())
print("bootstrap_ok")
