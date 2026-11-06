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
        "alembic==1.14.0",
        "psycopg2-binary",
        "pydantic",
        "pydantic-settings",
        "email-validator",
        "greenlet",
    ]
)
subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])
print("migrated_to_head")
